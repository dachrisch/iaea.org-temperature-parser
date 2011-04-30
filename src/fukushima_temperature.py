#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__="Christian Dähn"
__date__ ="$28.04.2011 18:03:30$"
import logging
logging.basicConfig(level=logging.INFO)

import re
log = logging.getLogger('parser')

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
