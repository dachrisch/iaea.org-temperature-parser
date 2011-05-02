#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__="Christian Dähn"
__date__ ="$28.04.2011 18:03:30$"
import logging
import logging.config
logging.config.fileConfig('logging.conf')

import re
log = logging.getLogger('parser')

class FukushimaSiteReports(object):
    def __init__(self):
        self.update_log_parser = UpdateLogSiteParser()
        self.unit_reports = {}

    def _read_from_url(self, url):
        from urllib import urlopen
        update_site = urlopen(url)
        log.debug('reading from update site (%s)' % update_site.url)
        content = update_site.read()
        return content

    def __get_updates_sites(self, update_site):
        update_log_sites = SiteLinksParser().parse_log_sites(self._read_from_url(update_site))

        sl = SiteLink('280411')
        sl.url = update_site
        update_log_sites.append(sl)

        return update_log_sites

    def update_from_update_sites(self, update_site='http://www.iaea.org/newscenter/news/tsunamiupdate01.html'):
        update_log_sites = self.__get_updates_sites(update_site)

        log.info('getting updates from [%d] sites...' % len(update_log_sites))
        for update_log_site in update_log_sites:
            log.info('parsing update site [%s]' % update_log_site.to_url())
            try:
                self.unit_reports[update_log_site.date] = self.update_log_parser.parse_to_unit_reports(self._read_from_url(update_log_site.to_url()))
            except NoSentencesParsedException, e:
                log.warn('error parsing from update site [%s]: %s' % (update_log_site.to_url(), e))
                log.debug(e, exc_info = 1)
            except Exception, e:
                log.error('error parsing from update site [%s]: %s' % (update_log_site.to_url(), e))
                log.debug(e,  exc_info = 1)
            log.debug('%s: %s' % (update_log_site.to_url(), self.unit_reports))

        log.info('all updates fetched.')
        return self.unit_reports

    def __determine_available_units_sorted(self):
        available_units_set = set()
        for unit_report in self.unit_reports.values():
            available_units_set.update(unit_report.keys())
        available_units = [report for report in available_units_set]
        available_units.sort()
        return available_units

    def __create_header_and_line_replacement_string(self, available_units):
        feedwater_header = []
        bottom_header = []
        feedwater_csv = []
        bottom_csv = []
        for unit in available_units:
            feedwater_header.append('feedwater_nozzle_temp_unit_%s' % unit)
            bottom_header.append('reactor_bottom_temp_unit_%s' % unit)
            feedwater_csv.append('%%(%s)s' % feedwater_header[-1])
            bottom_csv.append('%%(%s)s' % bottom_header[-1])

        header = 'date;%s;%s' % (';'.join(feedwater_header), ';'.join(bottom_header))
        csv_replace_line = '%%(date)s;%s;%s' % (';'.join(feedwater_csv), ';'.join(bottom_csv))

        return header, csv_replace_line

    def to_csv(self):
        csv_logger = logging.getLogger('fukushima.csv')
        available_units = self.__determine_available_units_sorted()
        header, csv_replace_line = self.__create_header_and_line_replacement_string(available_units)
        csv = [header, ]

        sorted_date_keys = sorted(self.unit_reports.keys(), key=lambda date: '%s/%s/%s' % (date[2:4], date[:2], date[4:]))
        for date in sorted_date_keys:
            data = {}
            unit_report = self.unit_reports[date]
            for unit in available_units:
                if unit in unit_report:
                    data['feedwater_nozzle_temp_unit_%s' % unit] = unit_report[unit].feedwater_nozzle_temp or -1
                    data['reactor_bottom_temp_unit_%s' % unit] = unit_report[unit].reactor_bottom_temp or -1
                else:
                    data['feedwater_nozzle_temp_unit_%s' % unit] = -1
                    data['reactor_bottom_temp_unit_%s' % unit] = -1
            data['date'] = '%s/%s/%s' % (date[2:4], date[:2], date[4:])
            csv.append(csv_replace_line % data)

        csv_string = '\n'.join(csv)
        csv_logger.info(csv_string)
        return csv_string

class SiteLink(object):
    def __init__(self, datestring):
        self.url = 'http://www.iaea.org/newscenter/news/2011/fukushima%s.html' % datestring
        self.date = datestring
    def to_url(self):
        return self.url

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
        self.nozzle_pattern = re.compile('feed[ -]?water nozzle of (?:the|Unit \d\'s) (?:reactor pressure vessel|RPV)')
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
                    log.debug('already accepted a unit report. ignoring further updates: %s' % unit)
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
                if self._has_temp(part):
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
                else:
                    log.debug('skipping no temperature part [%s]' % part)

class NoSentencesParsedException(Exception):
    pass

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
            raise NoSentencesParsedException('no sectences could be parsed from [%d] sentences' % len(potential_sentences))
            log.debug(potential_sentences)
        return captured_sentences

    def parse_to_unit_reports(self, content):
        sentences = self.parse_sentences(content)

        unit_parser = UnitSentenceParser()
        for sentence in sentences:
            unit_parser.accept(sentence)

        return unit_parser.all_valid_units()

if __name__ == '__main__':
    report_handler = FukushimaSiteReports()
    report_handler.update_from_update_sites('http://www.iaea.org/newscenter/news/tsunamiupdate01.html')

    print report_handler.to_csv()
