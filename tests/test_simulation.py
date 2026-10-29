"""End-to-end regressions; run inside the toolchain container."""
import unittest

from app import ROOT, app


class SimulationTests(unittest.TestCase):
    def simulate(self, pixels, weights, expected):
        with app.test_client() as client:
            response = client.post('/api/run', json={
                'pixels': pixels,
                'weights': weights,
                'source': (ROOT / 'rtl/conv2d.sv').read_text(),
            })
        data = response.get_json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual([row['actual'] for row in data['verification']], expected)
        self.assertTrue(all(row['passed'] for row in data['verification']))
        self.assertEqual(len(data['trace']), 36)
        self.assertIsNone(data['synthesis_error'])
        self.assertNotIn('%Warning-WIDTH', data['log'])
        return data

    def test_default_edge_kernel(self):
        data = self.simulate(
            [[r * 4 + c + 1 for c in range(4)] for r in range(4)],
            [[1, 0, -1]] * 3, [-6] * 4,
        )
        self.assertEqual(data['trace'][-1]['pixel'], 16)
        self.assertEqual(data['trace'][-1]['weight'], -1)

    def test_final_memory_entries_are_loaded(self):
        pixels = [[0] * 4 for _ in range(4)]
        weights = [[0] * 3 for _ in range(3)]
        pixels[3][3] = -128
        weights[2][2] = 127
        self.simulate(pixels, weights, [0, 0, 0, -16256])

    def test_signed_accumulator(self):
        self.simulate([[-128] * 4 for _ in range(4)],
                      [[-128] * 3 for _ in range(3)], [147456] * 4)


if __name__ == '__main__':
    unittest.main()
