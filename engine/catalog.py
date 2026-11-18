"""Every release the engine tracks: where its dates come from, when it lands, and which figures it reports.

components: (label, FRED series, transform)
  transforms: pct = % change on the prior period, yoy = % change on a year earlier, diff = change in level (thousands -> K),
              level1 = level with one decimal, pctlevel = level shown as %, rate = 2-decimal %, claims = persons -> K,
              claimsM = persons -> M, thousands = thousands -> K, millions = thousands -> M
The first component is the headline shown in the calendar row.
"""

# key: dict(...)  -- `fred` is a regex on FRED's release name, `rid` a fallback id
RELEASES = {
    "nfp": dict(fred=r"^Employment Situation$", rid=50, time="08:30", impact="high", src="BLS", lag=1,
                title="Non-farm payrolls · Employment situation ({per})",
                comps=[("Payrolls", "PAYEMS", "diff"), ("Unemployment rate", "UNRATE", "pctlevel"),
                       ("Avg hourly earnings m/m", "CES0500000003", "pct"), ("Avg hourly earnings y/y", "CES0500000003", "yoy")]),
    "cpi": dict(fred=r"^Consumer Price Index$", rid=10, time="08:30", impact="high", src="BLS", lag=1,
                title="CPI inflation ({per})",
                comps=[("Core CPI m/m", "CPILFESL", "pct"), ("CPI m/m", "CPIAUCSL", "pct"),
                       ("Core CPI y/y", "CPILFESL", "yoy"), ("CPI y/y", "CPIAUCSL", "yoy")]),
    "ppi": dict(fred=r"^Producer Price Index$", rid=46, time="08:30", impact="medium", src="BLS", lag=1,
                title="PPI producer prices ({per})",
                comps=[("PPI final demand m/m", "PPIFIS", "pct"), ("PPI ex food & energy m/m", "PPIFES", "pct"),
                       ("PPI final demand y/y", "PPIFIS", "yoy")]),
    "retail": dict(fred=r"^Advance Monthly Sales for Retail and Food Services$", rid=9, time="08:30", impact="high",
                   src="Census Bureau", lag=1, title="Retail sales ({per})",
                   comps=[("Retail sales m/m", "RSAFS", "pct"), ("Ex autos m/m", "RSFSXMV", "pct"), ("Retail sales y/y", "RSAFS", "yoy")]),
    "gdp": dict(fred=r"^Gross Domestic Product$", rid=53, time="08:30", impact="high", src="BEA", lag="quarter",
                title="GDP, {est} estimate ({per})",
                comps=[("Real GDP, annualized", "A191RL1Q225SBEA", "pctlevel")]),
    "pce": dict(fred=r"^Personal Income and Outlays$", rid=54, time="08:30", impact="high", src="BEA", lag=1,
                title="PCE inflation · Personal income and outlays ({per})",
                comps=[("Core PCE m/m", "PCEPILFE", "pct"), ("PCE m/m", "PCEPI", "pct"), ("Core PCE y/y", "PCEPILFE", "yoy"),
                       ("Personal spending m/m", "PCE", "pct"), ("Personal income m/m", "PI", "pct")]),
    "claims": dict(fred=r"^Unemployment Insurance Weekly Claims", rid=180, time="08:30", impact="medium",
                   src="Dept. of Labor", lag="week", title="Initial jobless claims",
                   comps=[("Initial claims", "ICSA", "claims"), ("4-week average", "IC4WSA", "claims"), ("Continuing claims", "CCSA", "claimsM")]),
    "jolts": dict(fred=r"^Job Openings and Labor Turnover Survey$", rid=192, time="10:00", impact="medium", src="BLS", lag=2,
                  title="JOLTS job openings ({per})",
                  comps=[("Job openings", "JTSJOL", "millions"), ("Quits rate", "JTSQUR", "pctlevel")]),
    "umich": dict(fred=r"^Surveys of Consumers$", rid=91, time="10:00", impact="medium", src="University of Michigan", lag=0,
                  title="UMich consumer sentiment, {stage} ({per})",
                  comps=[("Consumer sentiment", "UMCSENT", "level1"), ("1-yr inflation expectations", "MICH", "pctlevel")]),
    "durables": dict(fred=r"Durable Goods", rid=95, time="08:30", impact="medium", src="Census Bureau", lag=1,
                     title="Durable goods orders ({per})",
                     comps=[("Durable goods m/m", "DGORDER", "pct"), ("Ex transportation m/m", "ADXTNO", "pct")]),
    "homes": dict(fred=r"^New Residential Sales$", rid=97, time="10:00", impact="medium", src="Census Bureau", lag=1,
                  title="New home sales ({per})", comps=[("New home sales", "HSN1F", "thousands")]),
    "adp": dict(fred=r"^ADP National Employment Report$", rid=194, time="08:15", impact="medium", src="ADP", lag=1,
                title="ADP private payrolls ({per})", comps=[("ADP private payrolls", "ADPMNUSNERSA", "diff")]),
    "fomc": dict(fred=r"^FOMC Press Release$", rid=101, time="14:00", impact="high", src="Federal Reserve", lag=None,
                 title="FOMC rate decision", comps=[("Fed funds target, upper bound", "DFEDTARU", "rate")]),
}

# Releases whose dates follow a rule rather than a FRED calendar. No free figures for these.
RULED = {
    "ism-m": dict(time="10:00", impact="high", src="ISM", title="ISM Manufacturing PMI ({per})",
                  note="Usually the first business day of the month; confirm on ismworld.org."),
    "ism-s": dict(time="10:00", impact="medium", src="ISM", title="ISM Services PMI ({per})",
                  note="Usually the third business day of the month; confirm on ismworld.org."),
    "conf": dict(time="10:00", impact="medium", src="Conference Board", title="Consumer confidence ({per})",
                 note="Usually the last Tuesday of the month; confirm on conference-board.org."),
    "minutes": dict(time="14:00", impact="medium", src="Federal Reserve", title="FOMC minutes ({per} meeting)",
                    note="Released three weeks after each decision."),
    "beige": dict(time="14:00", impact="medium", src="Federal Reserve", title="Beige Book",
                  note="Usually two weeks before each Fed meeting; confirm on federalreserve.gov."),
}

NOTES = {
    "08:15": "Lands 75 minutes before the 9:30 open.",
    "08:30": "Lands an hour before the 9:30 open. Let the release candle print.",
    "10:00": "Lands at 10:00, inside the NY AM kill zone and the start of the Silver Bullet hour.",
    "14:00": "Released at 14:00 New York, during the NY PM session.",
}

NAMES = {"cpi": "Core CPI", "ppi": "PPI", "nfp": "Payrolls", "retail": "Retail sales", "gdp": "GDP",
         "pce": "Core PCE", "claims": "Jobless claims", "umich": "UMich sentiment", "durables": "Durable goods orders",
         "homes": "New home sales", "jolts": "Job openings", "fomc": "The Fed's rate decision", "ism-m": "ISM manufacturing",
         "ism-s": "ISM services", "adp": "ADP payrolls", "conf": "Consumer confidence", "ecb": "The ECB decision",
         "boe": "The BoE decision", "minutes": "The FOMC minutes", "beige": "The Beige Book"}

WHY = {
    "cpi": "Inflation decides whether the Fed can ease or must stay tight, so a surprise reprices rates, the dollar and stocks quickly.",
    "pce": "PCE is the Fed's preferred inflation gauge, measured against its 2% target.",
    "ppi": "Producer prices feed into parts of the Fed's preferred inflation measure.",
    "nfp": "Jobs and wages are half of the Fed's mandate, and payrolls are often the most volatile release of the month.",
    "retail": "Consumer spending is the biggest part of the US economy, so strong spending can keep rates higher for longer.",
    "gdp": "It's the broadest read on how fast the economy is growing.",
    "claims": "Claims are the most frequent check on layoffs.",
    "umich": "The survey's inflation expectations are watched by the Fed.",
    "durables": "Orders for long-lasting goods are a read on business investment.",
    "homes": "Housing reacts quickly to interest rates.",
    "jolts": "Openings show how tight the labour market is.",
    "fomc": "The rate decision, statement and press conference can reprice every market at once.",
    "minutes": "The minutes show how officials weighed the last decision.",
    "beige": "The Beige Book summarises conditions across the Fed's twelve districts.",
    "ism-m": "Factory activity is one of the first readings of each month.",
    "ism-s": "Services make up most of the US economy, and its prices index tracks sticky inflation.",
    "adp": "It's the first jobs number of the month, though not a reliable guide to payrolls.",
    "conf": "Its jobs questions are an early read on the labour market.",
    "ecb": "It moves the euro and, through it, the dollar index.",
    "boe": "It moves the pound; the vote split often matters as much as the decision.",
}

HISTORY_KEYS = {"cpi": "cpi", "nfp": "nfp", "retail": "retail", "pce": "pce", "ism-m": "ism", "gdp": "gdp"}

# Market pulse: public-domain daily/weekly series from the Fed, Treasury and EIA (via FRED)
MARKETS = [
    ("y2", "2-year Treasury", "DGS2", "yield"),
    ("y10", "10-year Treasury", "DGS10", "yield"),
    ("curve", "10y minus 2y", "T10Y2Y", "spread"),
    ("be10", "10-yr breakeven inflation", "T10YIE", "yield"),
    ("real10", "10-yr real yield", "DFII10", "yield"),
    ("effr", "Effective fed funds", "DFF", "yield"),
    ("usd", "Dollar index (Fed broad)", "DTWEXBGS", "index"),
    ("oil", "WTI crude oil", "DCOILWTICO", "price"),
    ("nfci", "Financial conditions (Chicago Fed)", "NFCI", "index2"),
    ("mort", "30-yr mortgage rate", "MORTGAGE30US", "yield"),
]
REACTION_SERIES = [("y2", "DGS2", "bp"), ("y10", "DGS10", "bp"), ("usd", "DTWEXBGS", "pct")]
REACTION_KEYS = ["cpi", "nfp", "pce", "retail", "ppi", "gdp", "fomc", "claims"]
