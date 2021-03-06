#!/usr/bin/python
# -*- coding: utf-8 -*-

__author__="Christian Dähn"
__date__ ="$28.04.2011 18:03:30$"

import re
import unittest
import sys
sys.path.append("../src")
import logging
#logging.basicConfig(level=logging.INFO)

log = logging.getLogger('test')

from fukushima_temperature import UnitSentenceParser, UpdateLogSiteParser, FukushimaSiteReports

class FukushimaTemperatureSentenceBasedTestCase(unittest.TestCase):

    def test_read_unit_from_sentence(self):
        sentence = '<p>The reactor pressure vessel temperatures in <strong>Unit 1</strong> remain above cold shutdown conditions.'
        self.assertEquals(UnitSentenceParser()._parse_unit(sentence), '1')

    def test_read_one_temperature_from_single_sentence(self):
        sentence = 'In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.'
                    

        pattern = re.compile('(?P<temp>[0-9\.]+) [°&;deg]{,5}C')
        m = pattern.search(sentence)
        self.assertEqual(m.group('temp'), '150')

    def test_read_two_temperatures_from_single_sentence(self):
        sentence = 'In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.'

        parts = sentence.split('and')
        pattern = re.compile('(?P<temp>[0-9\.]+) [°&;deg]{,5}C')
        m = pattern.search(parts[0])
        self.assertEqual(m.group('temp'), '91')
        m = pattern.search(parts[1])
        self.assertEqual(m.group('temp'), '121')

    def test_categorize_sentence(self):
        assert UnitSentenceParser()._is_unit_sentence('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_temp('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_nozzle_temp('In <strong>Unit 2</strong>, the temperature at the feed water nozzle of the RPV is 150 °C.')
        assert UnitSentenceParser()._has_bottom_temp('In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.')
        assert UnitSentenceParser()._is_multi_part_sentence('In <strong>Unit 3</strong> the temperature at the feed water nozzle of the RPV is 91 °C and at the bottom of the RPV is 121 °C.')

    def test_split_sentences_and_assign_sentences_to_unit(self):
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

    def test_accept_any_sentence_and_create_unit_or_assign_it(self):
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

    def test_parse_temperatures_from_html_file(self):
        with open('temperature_site.html', 'r') as temp_file:
            content = temp_file.read()

        units_reports = UpdateLogSiteParser().parse_to_unit_reports(content)

        self.assertEqual(len(units_reports), 3)
        self.assertEqual(units_reports['1'].unit, '1')
        self.assertEqual(units_reports['2'].unit, '2')
        self.assertEqual(units_reports['3'].unit, '3')

        self.assertEqual('111', units_reports['1'].reactor_bottom_temp, units_reports['1'])
        self.assertEqual(None, units_reports['2'].reactor_bottom_temp)

    def test_parse_special_update(self):
        with open('fukushima290311.html', 'r') as file:
            content = file.read()
        units_reports = UpdateLogSiteParser().parse_to_unit_reports(content)

        self.assertEqual(len(units_reports), 2)
        self.assertEqual(units_reports['1'].unit, '1')
        self.assertEqual(units_reports['3'].unit, '3')
                
    def test_create_csv_report(self):
        with open('temperature_site.html', 'r') as temp_file:
            content = temp_file.read()

        units_reports = UpdateLogSiteParser().parse_to_unit_reports(content)

        reports = FukushimaSiteReports()
        reports.unit_reports = {'042211' : units_reports}

        (header, csv_line) = reports.to_csv().split('\n')

        self.assertEqual(header, 'date;feedwater_nozzle_temp_unit_1;feedwater_nozzle_temp_unit_2;feedwater_nozzle_temp_unit_3;reactor_bottom_temp_unit_1;reactor_bottom_temp_unit_2;reactor_bottom_temp_unit_3')
        self.assertEqual(csv_line, '22/04/11;138;123;75;111;-1;111')
    def xtest_live_fetch_first_site_and_all_depending(self):
        report_handler = FukushimaSiteReports()
        report_handler.update_from_update_sites('http://www.iaea.org/newscenter/news/tsunamiupdate01.html')

        print report_handler.to_csv()


if __name__ == '__main__':
    unittest.main()

