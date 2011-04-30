#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__="Christian Dähn"
__date__ ="$28.04.2011 18:03:30$"

import re
import unittest
import sys
sys.path.append("../src")
import logging
logging.basicConfig(level=logging.INFO)

log = logging.getLogger('test')

class SiteLink(object):
    def __init__(self, datestring):
        self.date = datestring
    def to_url(self):
        return 'http://www.iaea.org/newscenter/news/2011/fukushima%s.html' % self.date

class SiteLinksParser(object):
    def parse_log_sites(self, content):
        pattern = re.compile('<a href="/newscenter/news/2011/fukushima(\d{6}).html">(\d+) (\w+)</a>')

        list_m = pattern.findall(content)

        sites = {}
        for m in list_m:
            sites[m[0]] = SiteLink(m[0])

        return sites.values()

class Unit(object):
    def __init__(self, unit):
        self.unit = unit
        self.feedwater_nozzle_temp = None
        self.reactor_bottom_temp = None
    def is_valid(self):
        return self.unit and (self.feedwater_nozzle_temp or self.reactor_bottom_temp)
    def __repr__(self):
        return ''.join(('unit %(unit)s',
                        (self.feedwater_nozzle_temp and ' temperature is %(feedwater_nozzle_temp)s °C at nozzle') or '',
                        self.reactor_bottom_temp and (' and %(reactor_bottom_temp)s °C at bottom' % self.__dict__) or ''
                        )) % self.__dict__

class UnitSentenceParser(object):
    def __init__(self):
        self.unit_pattern = re.compile('<strong>Unit (?P<unit>\d)</strong>')
        self.nozzle_pattern = re.compile('feed[ -]?water nozzle of the (?:reactor pressure vessel|RPV)')
        self.bottom_pattern = re.compile('bottom of(?: the)? (?:reactor pressure vessel|RPV)')
        self.temp_pattern = re.compile('(?P<temp>[0-9.]+) [°;&deg]+C')
        self.units = {}
        self.multipart_indicator = ' and '
        self.currently_parsed_unit = None

    def _is_unit_sentence(self, sentence):
        return self.unit_pattern.search(sentence) is not None

    def _parse_unit(self, sentence):
        if self._is_unit_sentence(sentence):
            unit = self.unit_pattern.search(sentence).group('unit')
            log.debug('parsed unit [%s] from [%s]' % (unit, sentence))
            return unit

    def _has_temp(self, sentence):
        return self.temp_pattern.search(sentence) is not None

    def _has_nozzle_temp(self, sentence):
        return self.nozzle_pattern.search(sentence) is not None

    def _has_bottom_temp(self, sentence):
        return self.bottom_pattern.search(sentence) is not None

    def _is_multi_part_sentence(self, sentence):
        return self.multipart_indicator in sentence

    def all_valid_units(self):
        for k, v in self.units.items():
            if not v.is_valid():
                del self.units[k]
        return self.units

    def accept(self, sentence):
        if self._is_unit_sentence(sentence):
            unit = self._parse_unit(sentence)
            log.debug('detected new unit sentence for unit (%s): %s' % (unit, sentence))
            self.currently_parsed_unit = Unit(unit)
            if unit in self.units.keys():
                if self.units[unit].is_valid():
                    log.warn('already accepted a unit report. ignoring further updates: %s' % unit)
                    self.currently_parsed_unit = None
                    return
                else:
                    log.debug('ignoring previous invalid unit recording [%s]' % self.units[unit])
                    del self.units[unit]
            self.units[unit] = self.currently_parsed_unit
        if self.currently_parsed_unit and self._has_temp(sentence):
            if self._is_multi_part_sentence(sentence):
                log.debug('splitting multi-part sentence [%s]' % sentence)
                parts = sentence.split(self.multipart_indicator)
            else:
                parts = (sentence, )

            for part in parts:
                temperature = self.temp_pattern.search(part).group('temp')
                log.debug('parsed temparature [%s] from [%s] for [%s]' % (temperature, part, self.currently_parsed_unit))
                if self._has_bottom_temp(part):
                    self.currently_parsed_unit.reactor_bottom_temp = temperature
                elif self._has_nozzle_temp(part):
                    self.currently_parsed_unit.feedwater_nozzle_temp = temperature
                elif 'spent fuel ' in part.lower() or 'spraying' in part or 'cold shutdown conditions' in part:
                    pass # ignore
                else:
                    raise Exception('could not determine temperature type from [%s]' % part)

class UpdateLogSiteParser(object):
    def parse_sentences(self, content):
        potential_sentences = []
        for c in content.split('</p>'):
            potential_sentences.extend([s.strip() for s in c.split('. ')])

        capturing = False
        captured_sentences = []
        for potential_sentence in potential_sentences:
            if not capturing and ('<p><strong>Plant status</strong>' in potential_sentence or 'Current Situation' in potential_sentence):
                log.debug('start capturing from sentence [%s]' % potential_sentence)
                capturing = True
                continue
            if capturing:
                if 'Radiation Monitoring' in potential_sentence:
                    log.debug('stop capturing from sentence [%s]' % potential_sentence)
                    break
                log.debug('capturing sentence [%s]' % potential_sentence)
                captured_sentences.append(potential_sentence)

        if not captured_sentences:
            log.error('no sectences could be parsed from [%s]' % potential_sentences)
        return captured_sentences

    def parse_to_unit_reports(self, content):
        sentences = self.parse_sentences(content)

        unit_parser = UnitSentenceParser()
        for sentence in sentences:
            unit_parser.accept(sentence)

        return unit_parser.all_valid_units()

class FukushimaTemperatureSentenceBasedTestCase(unittest.TestCase):

    def xtest_read_unit_from_sentence(self):
        sentence = '<p>The reactor pressure vessel temperatures in <strong>Unit 1</strong> remain above cold shutdown conditions.'
        self.assertEquals(UnitSentenceParser()._parse_unit(sentence), '1')

    def xtest_read_one_temperature_from_single_sentence(self):
        sentence = 'In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.'
                    

        pattern = re.compile('(?P<temp>[0-9\.]+) [°&;deg]{,5}C')
        m = pattern.search(sentence)
        self.assertEqual(m.group('temp'), '150')

    def xtest_read_two_temperatures_from_single_sentence(self):
        sentence = 'In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.'

        parts = sentence.split('and')
        pattern = re.compile('(?P<temp>[0-9\.]+) [°&;deg]{,5}C')
        m = pattern.search(parts[0])
        self.assertEqual(m.group('temp'), '91')
        m = pattern.search(parts[1])
        self.assertEqual(m.group('temp'), '121')

    def xtest_categorize_sentence(self):
        assert UnitSentenceParser()._is_unit_sentence('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_temp('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_nozzle_temp('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_bottom_temp('In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.')
        assert UnitSentenceParser()._is_multi_part_sentence('In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.')

    def xtest_split_sentences_and_assign_sentences_to_unit(self):
        long_sentence = 'In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.  In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.'
        sentences = long_sentence.split('.')

        unit_parser = UnitSentenceParser()
        unit_sentence_assignments = {}
        current_unit = None
        for sentence in sentences:
            if unit_parser._is_unit_sentence(sentence):
                current_unit = unit_parser._parse_unit(sentence)
                if current_unit not in unit_sentence_assignments.keys():
                    unit_sentence_assignments[current_unit] = []
            if current_unit:
                unit_sentence_assignments[current_unit].append(sentence)

        keys = unit_sentence_assignments.keys()
        keys.sort()
        self.assertEqual(keys, ['2', '3'])

    def xtest_accept_any_sentence_and_create_unit_or_assign_it(self):
        long_sentence = '''<p>The reactor pressure vessel temperatures in <strong>Unit 1</strong> remain above cold shutdown conditions. The indicated temperature at the feedwater nozzle of the reactor pressure vessel is 138 &deg;C and at the bottom of reactor pressure vessel is 111 &deg;C.</p>
<p>The reactor pressure vessel temperatures in <strong>Unit 2</strong> remain above cold shutdown conditions. The indicated temperature at the feed water nozzle of the reactor pressure vessel is 123 &deg;C. The reactor pressure vessel and the dry well remain at atmospheric pressure. Fresh water injection (approximately 38 tonnes) to the spent fuel pool via the spent fuel pool cooling line was carried out on 25 April.</p>
<p>The temperature at the bottom of the reactor pressure vessel in <strong>Unit 3</strong> remains above cold shutdown conditions. The indicated temperature at the feed water nozzle of the reactor pressure vessel is 75 &deg;C and at the bottom of the reactor pressure vessel is 111 &deg;C. The reactor pressure vessel and the dry well remain at atmospheric pressure.</p>
'''
        sentences = long_sentence.split('.')

        unit_parser = UnitSentenceParser()
        for sentence in sentences:
            unit_parser.accept(sentence)

        self.assertEqual(len(unit_parser.units), 3)

        self.assertEqual(unit_parser.units['1'].feedwater_nozzle_temp, '138')
        self.assertEqual(unit_parser.units['2'].feedwater_nozzle_temp, '123')
        self.assertEqual(unit_parser.units['3'].feedwater_nozzle_temp, '75')
        self.assertEqual(unit_parser.units['3'].reactor_bottom_temp, '111')

    def xtest_parse_temperatures_from_html_file(self):
        with open('temperature_site.html', 'r') as temp_file:
            content = temp_file.read()

        units_reports = UpdateLogSiteParser().parse_to_unit_reports(content)

        self.assertEqual(len(units_reports), 3)
        self.assertEqual(units_reports['1'].unit, '1')
        self.assertEqual(units_reports['2'].unit, '2')
        self.assertEqual(units_reports['3'].unit, '3')

        self.assertEqual('111', units_reports['1'].reactor_bottom_temp, units_reports['1'])
        self.assertEqual(None, units_reports['2'].reactor_bottom_temp)

    def xtest_parse_special_update(self):
        with open('fukushima290311.html', 'r') as file:
            content = file.read()
        units_reports = UpdateLogSiteParser().parse_to_unit_reports(content)

        print(units_reports)
        self.assertEqual(len(units_reports), 2)
        self.assertEqual(units_reports['1'].unit, '1')
        self.assertEqual(units_reports['3'].unit, '3')
                
    def _read_from_url(self, url):
        from urllib import urlopen
        update_site = urlopen(url)
        log.debug('reading from update site (%s)' % update_site.url)
        content = update_site.read()
        return content

    def test_live_fetch_first_site_and_all_depending(self):

        unit_reports = {}
        update_log_parser = UpdateLogSiteParser()

        count = 0

        update_log_sites = SiteLinksParser().parse_log_sites(self._read_from_url('http://www.iaea.org/newscenter/news/tsunamiupdate01.html'))

        for update_log_site in update_log_sites:
            log.info('parsing update site [%s]' % update_log_site.to_url())
            unit_reports[update_log_site.date] = update_log_parser.parse_to_unit_reports(self._read_from_url(update_log_site.to_url()))
            log.debug('%s: %s' % (update_log_site.to_url(), unit_reports))
            count += 1
            if count > 5: break

        print unit_reports


if __name__ == '__main__':
    unittest.main()

