import unittest
import numpy as np
from realtime.wafer_classifier import extract, official_labels
from realtime.data import manifest, read_wafer


class WaferClassifierTests(unittest.TestCase):
    def test_identifiers_do_not_change_features(self):
        entry=next(e for e in manifest() if int(e['wafer'])==4)
        columns,rows,x=read_wafer(entry)
        original=extract(columns,rows[:16],x[:16])
        changed=[r.copy() for r in rows[:16]]
        for r in changed:r[:3]=['unknown-part','different-lot','999']
        self.assertEqual(original,extract(columns,changed,x[:16]))
        self.assertEqual(len(original),44)
        self.assertTrue(np.isfinite(list(original.values())).all())

    def test_site_difference_is_measured(self):
        columns=['220_Main.Suite1#CP']+[f'{100+n}_Main.sensor{n}#CP' for n in range(1,7)]
        rows=[[str(i),'lot','1',str(i%4+1),'0','0','0'] for i in range(16)]
        x=np.tile(np.arange(16)[:,None]%2,(1,7)).astype(float)
        base=extract(columns,rows,x)
        rows[0][6]='8'
        modified=extract(columns,rows,x)
        self.assertEqual(modified['fail_fraction'],1/16)
        self.assertEqual(modified['site_fail_range'],.25)
        self.assertGreater(base['s0_site_mean_gap'],0)

    def test_insufficient_prefix_rejected_and_labels_exact(self):
        entry=next(e for e in manifest() if int(e['wafer'])==4)
        cols,rows,x=read_wafer(entry)
        with self.assertRaises(ValueError):extract(cols,rows[:8],x[:8])
        labels=official_labels()
        self.assertEqual(labels[1],'Site unbalance')
        self.assertEqual(len(set(labels.values())),7)


if __name__=='__main__':unittest.main()
