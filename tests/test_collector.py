import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collect_market import parse_date, parse_row, normalize, run

class CollectorTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(parse_date('1151120'),'2026-11-20')
        self.assertEqual(parse_date('20261120'),'2026-11-20')
        self.assertEqual(parse_date('115/11/20'),'2026-11-20')
        self.assertIsNone(parse_date('1151332'))
    def test_invalid_ohlc(self):
        row={'Code':'2330','Date':'1151120','OpeningPrice':'500','HighestPrice':'499','LowestPrice':'490','ClosingPrice':'498','TradeVolume':'100'}
        self.assertIsNone(parse_row(row,'twse'))
    def test_stale_or_incomplete_rejected(self):
        d=datetime(2026,11,23,12,0,tzinfo=ZoneInfo('Asia/Taipei'))
        rows=[{'Code':str(1000+i),'Date':'1151123','OpeningPrice':'5','HighestPrice':'6','LowestPrice':'4','ClosingPrice':'5','TradeVolume':'200'} for i in range(300)]
        with self.assertRaisesRegex(ValueError,'not final'):
            normalize(rows,'twse',d.date(),d.time())
    def test_publish_two_markets_and_preserve_when_one_source_fails(self):
        def data(market):
            code='Code' if market=='twse' else 'SecuritiesCompanyCode'
            return [{code:str(1000+i),'Date':'1151120','OpeningPrice':'10','HighestPrice':'11','LowestPrice':'9','ClosingPrice':'10','TradeVolume':'1'} for i in range(300)]
        def fetch(url): return data('twse' if 'twse' in url else 'tpex')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            now=datetime(2026,11,22,12,0,tzinfo=ZoneInfo('Asia/Taipei'))
            m=run(fetch,now,root)
            self.assertEqual(m['latest_by_market'],{'twse':'2026-11-20','tpex':'2026-11-20'})
            self.assertEqual(len(m['days']),1)
            p=root/'docs'/'daily'/'2026-11-20.json'
            self.assertEqual(len(json.loads(p.read_text())['markets']),2)
            def fail_tpex(url):
                if 'tpex' in url: raise OSError('offline')
                return data('twse')
            m2=run(fail_tpex,now,root)
            self.assertEqual(m2['latest_by_market']['tpex'],'2026-11-20')
            self.assertEqual(len(json.loads(p.read_text())['markets']),2)
            self.assertEqual(len(m2['warning']),1)

if __name__=='__main__':unittest.main()
