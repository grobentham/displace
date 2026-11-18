import time, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
URLS={
 "fred_csv":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICSA&cosd=2026-09-01",
 "alfred_csv":"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=ICSA&cosd=2026-09-01&coed=2026-11-13&vintage_date=2026-11-13",
 "alfred_dl":"https://alfred.stlouisfed.org/series/downloaddata?seid=ICSA",
 "fred_api_host":"https://api.stlouisfed.org/fred/series?series_id=GDP",
 "dol_ar539":"https://oui.doleta.gov/unemploy/csv/ar539.csv",
 "dol_pdf":"https://www.dol.gov/ui/data.pdf",
 "dol_claims_page":"https://oui.doleta.gov/unemploy/claims.asp",
 "census_advm3":"https://api.census.gov/data/timeseries/eits/advm3?get=cell_value,data_type_code,category_code,seasonally_adj,time_slot_id&time=from+2026-06",
 "census_ressales":"https://api.census.gov/data/timeseries/eits/ressales?get=cell_value,data_type_code,category_code,seasonally_adj&time=from+2026-06",
 "census_marts":"https://api.census.gov/data/timeseries/eits/marts?get=cell_value,data_type_code,category_code,seasonally_adj&time=from+2026-06",
 "umich_csv":"https://www.sca.isr.umich.edu/files/tbmics.csv",
 "umich_infl":"https://www.sca.isr.umich.edu/files/tbmpx1px5.csv",
 "fed_h10_page":"https://www.federalreserve.gov/releases/h10/current/default.htm",
 "fed_h10_broad":"https://www.federalreserve.gov/releases/h10/summary/indexb_b.htm",
 "fed_ddp":"https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H10",
 "eia_wti_xls":"https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls",
 "eia_wti_html":"https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RWTC&f=D",
 "chicagofed_nfci":"https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv",
 "freddie_pmms":"https://www.freddiemac.com/pmms/docs/PMMS_history.csv",
 "treasury_real":"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value=2026",
 "nyfed_effr_hist":"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2010-01-01&endDate=2010-03-01",
 "stooq_xau":"https://stooq.com/q/d/l/?s=xauusd&i=d",
 "stooq_ndx":"https://stooq.com/q/d/l/?s=^ndx&i=d",
 "yahoo_xau_spot":"https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=5d&interval=1d",
 "yahoo_dxy":"https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=5d&interval=1d",
 "yahoo_eurusd":"https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?range=5d&interval=1d",
 "yahoo_wti":"https://query1.finance.yahoo.com/v8/finance/chart/CL=F?range=5d&interval=1d",
 "philly_rtdsm_page":"https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists",
 "bls_schedule_cpi":"https://www.bls.gov/schedule/news_release/cpi.htm",
 "bls_archive_cpi":"https://www.bls.gov/bls/news-release/cpi.htm",
 "bls_v1_hist":"https://api.bls.gov/publicAPI/v1/timeseries/data/CUSR0000SA0L1E",
 "adp":"https://adpemploymentreport.com/",
 "bea_schedule":"https://www.bea.gov/news/schedule",
 "census_retail_hist":"https://www.census.gov/retail/marts/www/adv_table1.xlsx",
}
for k,u in URLS.items():
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20)
        b=r.read(3_000_000)
        print(f"PROBE {k} OK {r.status} {len(b)}B {time.time()-t:.1f}s {r.headers.get('Content-Type')} :: {b[:300]!r}")
    except Exception as e:
        body=b""
        try: body=e.read()[:200]
        except Exception: pass
        print(f"PROBE {k} FAIL {time.time()-t:.1f}s {e!r} :: {body!r}")
