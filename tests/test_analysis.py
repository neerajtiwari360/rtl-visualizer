import unittest
from unittest.mock import Mock

from rtl_analysis import analyze_project, parse_vcd, validate_project


class VcdTests(unittest.TestCase):
    def test_hierarchy_aliases_unknowns_and_timescale(self):
        wave = parse_vcd('''$timescale 1 ps $end
$scope module tb $end
$var wire 1 ! clk $end
$scope module dut $end
$var wire 1 ! clk $end
$var wire 8 # count [7:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
bx #
$end
#5
1!
b11111111 #
#10
0!
''')
        self.assertEqual(wave['timescale'], '1 ps')
        self.assertEqual(wave['end_time'], 10)
        self.assertEqual(wave['signals'][1]['name'], 'tb.dut.clk')
        self.assertEqual(wave['signals'][0]['changes'], [[0, '0'], [5, '1'], [10, '0']])
        self.assertEqual(wave['signals'][0]['changes'], wave['signals'][1]['changes'])
        self.assertEqual(wave['signals'][2]['changes'], [[0, 'x'], [5, '11111111']])


class ProjectTests(unittest.TestCase):
    def project(self):
        return dict(files=[dict(name='counter.sv', role='design', content='module counter; endmodule')],
                    top='counter', sim_top='tb_counter', action='lint')

    def test_rejects_path_traversal_duplicate_names_and_script_injection(self):
        for filename in ('../bad.sv', '/bad.sv', 'bad;exec.sv'):
            p = self.project(); p['files'][0]['name'] = filename
            with self.assertRaises(ValueError):
                validate_project(p)
        p = self.project(); p['top'] = 'counter; exec shell'
        with self.assertRaises(ValueError):
            validate_project(p)
        p = self.project(); p['files'] *= 2
        with self.assertRaises(ValueError):
            validate_project(p)

    def test_lint_only_needs_no_testbench(self):
        runner = Mock(return_value='Lint completed')
        result = analyze_project(self.project(), runner)
        self.assertTrue(result['stages']['lint']['ok'])
        self.assertEqual(runner.call_count, 1)
        self.assertIn('--lint-only', runner.call_args.args[0])

    def test_independent_stages_survive_tool_failure(self):
        p = self.project(); p['action'] = 'all'
        result = analyze_project(p, Mock(side_effect=ValueError('Compiler error')))
        self.assertEqual(set(result['stages']), {'lint', 'synthesis', 'simulation'})
        self.assertTrue(all(not stage['ok'] for stage in result['stages'].values()))


class GenericIntegrationTests(unittest.TestCase):
    def test_counter_project(self):
        from app import app
        with app.test_client() as client:
            project = client.get('/api/example/counter').get_json()
            response = client.post('/api/analyze', json={**project, 'action': 'all'})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(all(s['ok'] for s in data['stages'].values()), data['stages'])
        self.assertIn('PASS: counter', data['stages']['simulation']['log'])
        self.assertTrue(data['schematic'])
        count = next(s for s in data['waveform']['signals'] if s['name'].endswith('.count'))
        self.assertEqual(int(count['changes'][-1][1], 2), 10)


if __name__ == '__main__':
    unittest.main()
