"""
Step 1 — NSE Stock Name to Symbol Mapping Generator
Generates nse_stocks.json with 500 major NSE stocks.

This file powers the search feature:
  User types "Reliance" → fuzzy match → "RELIANCE.NS"

Run: python generate_nse_mapping.py
Output: nse_stocks.json
"""

import json

# ─────────────────────────────────────────────────────────────
# NSE 500 stocks — name, symbol, sector
# Symbol format: SYMBOL.NS  (yfinance NSE format)
#                SYMBOL.BO  (yfinance BSE format — kept as reference)
# ─────────────────────────────────────────────────────────────

NSE_STOCKS = [
    # ── LARGE CAP / NIFTY 50 ──────────────────────────────────
    {"name": "Reliance Industries", "symbol": "RELIANCE.NS", "sector": "Energy", "keywords": ["reliance", "ril", "jio"]},
    {"name": "Tata Consultancy Services", "symbol": "TCS.NS", "sector": "IT", "keywords": ["tcs", "tata consultancy"]},
    {"name": "HDFC Bank", "symbol": "HDFCBANK.NS", "sector": "Banking", "keywords": ["hdfc bank", "hdfc"]},
    {"name": "Infosys", "symbol": "INFY.NS", "sector": "IT", "keywords": ["infosys", "infy"]},
    {"name": "ICICI Bank", "symbol": "ICICIBANK.NS", "sector": "Banking", "keywords": ["icici", "icici bank"]},
    {"name": "Hindustan Unilever", "symbol": "HINDUNILVR.NS", "sector": "FMCG", "keywords": ["hul", "hindustan unilever", "unilever"]},
    {"name": "ITC Limited", "symbol": "ITC.NS", "sector": "FMCG", "keywords": ["itc"]},
    {"name": "State Bank of India", "symbol": "SBIN.NS", "sector": "Banking", "keywords": ["sbi", "state bank", "sbin"]},
    {"name": "Bharti Airtel", "symbol": "BHARTIARTL.NS", "sector": "Telecom", "keywords": ["airtel", "bharti airtel"]},
    {"name": "Kotak Mahindra Bank", "symbol": "KOTAKBANK.NS", "sector": "Banking", "keywords": ["kotak", "kotak bank"]},
    {"name": "Larsen & Toubro", "symbol": "LT.NS", "sector": "Infrastructure", "keywords": ["l&t", "larsen toubro", "lt"]},
    {"name": "Axis Bank", "symbol": "AXISBANK.NS", "sector": "Banking", "keywords": ["axis bank", "axis"]},
    {"name": "Asian Paints", "symbol": "ASIANPAINT.NS", "sector": "Paints", "keywords": ["asian paints"]},
    {"name": "HCL Technologies", "symbol": "HCLTECH.NS", "sector": "IT", "keywords": ["hcl", "hcltech"]},
    {"name": "Wipro", "symbol": "WIPRO.NS", "sector": "IT", "keywords": ["wipro"]},
    {"name": "Maruti Suzuki", "symbol": "MARUTI.NS", "sector": "Auto", "keywords": ["maruti", "maruti suzuki", "suzuki"]},
    {"name": "Sun Pharmaceutical", "symbol": "SUNPHARMA.NS", "sector": "Pharma", "keywords": ["sun pharma", "sunpharma"]},
    {"name": "Bajaj Finance", "symbol": "BAJFINANCE.NS", "sector": "NBFC", "keywords": ["bajaj finance"]},
    {"name": "Titan Company", "symbol": "TITAN.NS", "sector": "Consumer", "keywords": ["titan"]},
    {"name": "Tata Motors", "symbol": "TATAMOTORS.NS", "sector": "Auto", "keywords": ["tata motors", "jlr"]},
    {"name": "UltraTech Cement", "symbol": "ULTRACEMCO.NS", "sector": "Cement", "keywords": ["ultratech", "ultratech cement"]},
    {"name": "Nestle India", "symbol": "NESTLEIND.NS", "sector": "FMCG", "keywords": ["nestle", "maggi"]},
    {"name": "Power Grid Corporation", "symbol": "POWERGRID.NS", "sector": "Power", "keywords": ["power grid", "pgcil"]},
    {"name": "NTPC", "symbol": "NTPC.NS", "sector": "Power", "keywords": ["ntpc"]},
    {"name": "Tech Mahindra", "symbol": "TECHM.NS", "sector": "IT", "keywords": ["tech mahindra", "techm"]},
    {"name": "Bajaj Finserv", "symbol": "BAJAJFINSV.NS", "sector": "Financial", "keywords": ["bajaj finserv"]},
    {"name": "JSW Steel", "symbol": "JSWSTEEL.NS", "sector": "Metals", "keywords": ["jsw steel", "jsw"]},
    {"name": "Tata Steel", "symbol": "TATASTEEL.NS", "sector": "Metals", "keywords": ["tata steel"]},
    {"name": "Hindalco Industries", "symbol": "HINDALCO.NS", "sector": "Metals", "keywords": ["hindalco", "novelis"]},
    {"name": "Dr Reddy Laboratories", "symbol": "DRREDDY.NS", "sector": "Pharma", "keywords": ["dr reddy", "drreddy"]},
    {"name": "Cipla", "symbol": "CIPLA.NS", "sector": "Pharma", "keywords": ["cipla"]},
    {"name": "Eicher Motors", "symbol": "EICHERMOT.NS", "sector": "Auto", "keywords": ["eicher", "royal enfield"]},
    {"name": "Hero MotoCorp", "symbol": "HEROMOTOCO.NS", "sector": "Auto", "keywords": ["hero", "hero motocorp"]},
    {"name": "Bajaj Auto", "symbol": "BAJAJ-AUTO.NS", "sector": "Auto", "keywords": ["bajaj auto"]},
    {"name": "Grasim Industries", "symbol": "GRASIM.NS", "sector": "Cement", "keywords": ["grasim"]},
    {"name": "IndusInd Bank", "symbol": "INDUSINDBK.NS", "sector": "Banking", "keywords": ["indusind", "indusind bank"]},
    {"name": "Britannia Industries", "symbol": "BRITANNIA.NS", "sector": "FMCG", "keywords": ["britannia"]},
    {"name": "Divi's Laboratories", "symbol": "DIVISLAB.NS", "sector": "Pharma", "keywords": ["divis", "divi lab"]},
    {"name": "Adani Enterprises", "symbol": "ADANIENT.NS", "sector": "Conglomerate", "keywords": ["adani enterprises", "adani"]},
    {"name": "Adani Ports", "symbol": "ADANIPORTS.NS", "sector": "Infrastructure", "keywords": ["adani ports", "apsez"]},
    {"name": "Coal India", "symbol": "COALINDIA.NS", "sector": "Mining", "keywords": ["coal india"]},
    {"name": "ONGC", "symbol": "ONGC.NS", "sector": "Energy", "keywords": ["ongc", "oil natural gas"]},
    {"name": "Apollo Hospitals", "symbol": "APOLLOHOSP.NS", "sector": "Healthcare", "keywords": ["apollo hospital", "apollo"]},
    {"name": "Shree Cement", "symbol": "SHREECEM.NS", "sector": "Cement", "keywords": ["shree cement"]},
    {"name": "Tata Consumer Products", "symbol": "TATACONSUM.NS", "sector": "FMCG", "keywords": ["tata consumer", "tata tea"]},
    {"name": "Divis Laboratories", "symbol": "DIVISLAB.NS", "sector": "Pharma", "keywords": ["divis lab"]},

    # ── BANKING & FINANCE ─────────────────────────────────────
    {"name": "Bank of Baroda", "symbol": "BANKBARODA.NS", "sector": "Banking", "keywords": ["bank of baroda", "bob"]},
    {"name": "Punjab National Bank", "symbol": "PNB.NS", "sector": "Banking", "keywords": ["pnb", "punjab national bank"]},
    {"name": "Canara Bank", "symbol": "CANBK.NS", "sector": "Banking", "keywords": ["canara bank"]},
    {"name": "Union Bank of India", "symbol": "UNIONBANK.NS", "sector": "Banking", "keywords": ["union bank"]},
    {"name": "Federal Bank", "symbol": "FEDERALBNK.NS", "sector": "Banking", "keywords": ["federal bank"]},
    {"name": "IDFC First Bank", "symbol": "IDFCFIRSTB.NS", "sector": "Banking", "keywords": ["idfc first", "idfc bank"]},
    {"name": "Bandhan Bank", "symbol": "BANDHANBNK.NS", "sector": "Banking", "keywords": ["bandhan bank"]},
    {"name": "RBL Bank", "symbol": "RBLBANK.NS", "sector": "Banking", "keywords": ["rbl bank"]},
    {"name": "Yes Bank", "symbol": "YESBANK.NS", "sector": "Banking", "keywords": ["yes bank"]},
    {"name": "Muthoot Finance", "symbol": "MUTHOOTFIN.NS", "sector": "NBFC", "keywords": ["muthoot", "muthoot finance"]},
    {"name": "Shriram Finance", "symbol": "SHRIRAMFIN.NS", "sector": "NBFC", "keywords": ["shriram finance"]},
    {"name": "Bajaj Holdings", "symbol": "BAJAJHLDNG.NS", "sector": "Financial", "keywords": ["bajaj holdings"]},
    {"name": "HDFC Life Insurance", "symbol": "HDFCLIFE.NS", "sector": "Insurance", "keywords": ["hdfc life"]},
    {"name": "SBI Life Insurance", "symbol": "SBILIFE.NS", "sector": "Insurance", "keywords": ["sbi life"]},
    {"name": "ICICI Prudential Life", "symbol": "ICICIPRULI.NS", "sector": "Insurance", "keywords": ["icici prudential"]},
    {"name": "LIC Housing Finance", "symbol": "LICHSGFIN.NS", "sector": "NBFC", "keywords": ["lic housing"]},
    {"name": "Cholamandalam Finance", "symbol": "CHOLAFIN.NS", "sector": "NBFC", "keywords": ["chola", "cholamandalam"]},
    {"name": "Manappuram Finance", "symbol": "MANAPPURAM.NS", "sector": "NBFC", "keywords": ["manappuram"]},

    # ── IT & TECHNOLOGY ───────────────────────────────────────
    {"name": "Mphasis", "symbol": "MPHASIS.NS", "sector": "IT", "keywords": ["mphasis"]},
    {"name": "L&T Technology Services", "symbol": "LTTS.NS", "sector": "IT", "keywords": ["ltts", "l&t tech"]},
    {"name": "Mindtree", "symbol": "MINDTREE.NS", "sector": "IT", "keywords": ["mindtree"]},
    {"name": "Persistent Systems", "symbol": "PERSISTENT.NS", "sector": "IT", "keywords": ["persistent"]},
    {"name": "Coforge", "symbol": "COFORGE.NS", "sector": "IT", "keywords": ["coforge", "niit tech"]},
    {"name": "Hexaware Technologies", "symbol": "HEXAWARE.NS", "sector": "IT", "keywords": ["hexaware"]},
    {"name": "Zensar Technologies", "symbol": "ZENSARTECH.NS", "sector": "IT", "keywords": ["zensar"]},
    {"name": "Mastech Digital", "symbol": "MASTECH.NS", "sector": "IT", "keywords": ["mastech"]},
    {"name": "KPIT Technologies", "symbol": "KPITTECH.NS", "sector": "IT", "keywords": ["kpit"]},
    {"name": "Tata Elxsi", "symbol": "TATAELXSI.NS", "sector": "IT", "keywords": ["tata elxsi"]},

    # ── AUTO & AUTO ANCILLARY ─────────────────────────────────
    {"name": "Mahindra & Mahindra", "symbol": "M&M.NS", "sector": "Auto", "keywords": ["mahindra", "m&m"]},
    {"name": "TVS Motor", "symbol": "TVSMOTOR.NS", "sector": "Auto", "keywords": ["tvs motor", "tvs"]},
    {"name": "Ashok Leyland", "symbol": "ASHOKLEY.NS", "sector": "Auto", "keywords": ["ashok leyland"]},
    {"name": "MRF", "symbol": "MRF.NS", "sector": "Auto Ancillary", "keywords": ["mrf", "tyres"]},
    {"name": "Apollo Tyres", "symbol": "APOLLOTYRE.NS", "sector": "Auto Ancillary", "keywords": ["apollo tyres"]},
    {"name": "Bosch", "symbol": "BOSCHLTD.NS", "sector": "Auto Ancillary", "keywords": ["bosch"]},
    {"name": "Motherson Sumi", "symbol": "MOTHERSUMI.NS", "sector": "Auto Ancillary", "keywords": ["motherson"]},
    {"name": "Exide Industries", "symbol": "EXIDEIND.NS", "sector": "Auto Ancillary", "keywords": ["exide"]},
    {"name": "Amara Raja Batteries", "symbol": "AMARAJABAT.NS", "sector": "Auto Ancillary", "keywords": ["amara raja"]},

    # ── PHARMA & HEALTHCARE ───────────────────────────────────
    {"name": "Lupin", "symbol": "LUPIN.NS", "sector": "Pharma", "keywords": ["lupin"]},
    {"name": "Aurobindo Pharma", "symbol": "AUROPHARMA.NS", "sector": "Pharma", "keywords": ["aurobindo"]},
    {"name": "Alkem Laboratories", "symbol": "ALKEM.NS", "sector": "Pharma", "keywords": ["alkem"]},
    {"name": "Torrent Pharma", "symbol": "TORNTPHARM.NS", "sector": "Pharma", "keywords": ["torrent pharma"]},
    {"name": "Biocon", "symbol": "BIOCON.NS", "sector": "Pharma", "keywords": ["biocon"]},
    {"name": "Glenmark Pharma", "symbol": "GLENMARK.NS", "sector": "Pharma", "keywords": ["glenmark"]},
    {"name": "Max Healthcare", "symbol": "MAXHEALTH.NS", "sector": "Healthcare", "keywords": ["max healthcare", "max hospital"]},
    {"name": "Fortis Healthcare", "symbol": "FORTIS.NS", "sector": "Healthcare", "keywords": ["fortis"]},
    {"name": "Narayana Hrudayalaya", "symbol": "NH.NS", "sector": "Healthcare", "keywords": ["narayana", "nh"]},

    # ── FMCG & CONSUMER ──────────────────────────────────────
    {"name": "Dabur India", "symbol": "DABUR.NS", "sector": "FMCG", "keywords": ["dabur"]},
    {"name": "Godrej Consumer Products", "symbol": "GODREJCP.NS", "sector": "FMCG", "keywords": ["godrej consumer", "gcpl"]},
    {"name": "Marico", "symbol": "MARICO.NS", "sector": "FMCG", "keywords": ["marico", "parachute"]},
    {"name": "Colgate Palmolive", "symbol": "COLPAL.NS", "sector": "FMCG", "keywords": ["colgate"]},
    {"name": "Emami", "symbol": "EMAMILTD.NS", "sector": "FMCG", "keywords": ["emami"]},
    {"name": "Varun Beverages", "symbol": "VBL.NS", "sector": "FMCG", "keywords": ["varun beverages", "pepsi bottler"]},
    {"name": "United Spirits", "symbol": "MCDOWELL-N.NS", "sector": "FMCG", "keywords": ["united spirits", "mcdowell"]},
    {"name": "United Breweries", "symbol": "UBL.NS", "sector": "FMCG", "keywords": ["united breweries", "kingfisher beer"]},

    # ── ENERGY & POWER ────────────────────────────────────────
    {"name": "Adani Green Energy", "symbol": "ADANIGREEN.NS", "sector": "Renewable Energy", "keywords": ["adani green"]},
    {"name": "Adani Total Gas", "symbol": "ATGL.NS", "sector": "Energy", "keywords": ["adani total gas"]},
    {"name": "Indian Oil Corporation", "symbol": "IOC.NS", "sector": "Energy", "keywords": ["ioc", "indian oil"]},
    {"name": "Bharat Petroleum", "symbol": "BPCL.NS", "sector": "Energy", "keywords": ["bpcl", "bharat petroleum"]},
    {"name": "Hindustan Petroleum", "symbol": "HINDPETRO.NS", "sector": "Energy", "keywords": ["hpcl", "hindustan petroleum"]},
    {"name": "Tata Power", "symbol": "TATAPOWER.NS", "sector": "Power", "keywords": ["tata power"]},
    {"name": "Torrent Power", "symbol": "TORNTPOWER.NS", "sector": "Power", "keywords": ["torrent power"]},
    {"name": "CESC", "symbol": "CESC.NS", "sector": "Power", "keywords": ["cesc"]},
    {"name": "JSW Energy", "symbol": "JSWENERGY.NS", "sector": "Power", "keywords": ["jsw energy"]},

    # ── INFRASTRUCTURE & REAL ESTATE ─────────────────────────
    {"name": "DLF", "symbol": "DLF.NS", "sector": "Real Estate", "keywords": ["dlf"]},
    {"name": "Godrej Properties", "symbol": "GODREJPROP.NS", "sector": "Real Estate", "keywords": ["godrej properties"]},
    {"name": "Oberoi Realty", "symbol": "OBEROIRLTY.NS", "sector": "Real Estate", "keywords": ["oberoi realty"]},
    {"name": "Prestige Estates", "symbol": "PRESTIGE.NS", "sector": "Real Estate", "keywords": ["prestige"]},
    {"name": "Brigade Enterprises", "symbol": "BRIGADE.NS", "sector": "Real Estate", "keywords": ["brigade"]},
    {"name": "IRB Infrastructure", "symbol": "IRB.NS", "sector": "Infrastructure", "keywords": ["irb infra"]},
    {"name": "GMR Airports", "symbol": "GMRINFRA.NS", "sector": "Infrastructure", "keywords": ["gmr", "gmr airports"]},

    # ── METALS & MINING ───────────────────────────────────────
    {"name": "Vedanta", "symbol": "VEDL.NS", "sector": "Metals", "keywords": ["vedanta"]},
    {"name": "National Aluminium", "symbol": "NATIONALUM.NS", "sector": "Metals", "keywords": ["nalco", "national aluminium"]},
    {"name": "Steel Authority of India", "symbol": "SAIL.NS", "sector": "Metals", "keywords": ["sail", "steel authority"]},
    {"name": "NMDC", "symbol": "NMDC.NS", "sector": "Mining", "keywords": ["nmdc"]},
    {"name": "Hindustan Zinc", "symbol": "HINDZINC.NS", "sector": "Metals", "keywords": ["hindustan zinc"]},
    {"name": "APL Apollo Tubes", "symbol": "APLAPOLLO.NS", "sector": "Metals", "keywords": ["apl apollo"]},

    # ── TELECOM ───────────────────────────────────────────────
    {"name": "Vodafone Idea", "symbol": "IDEA.NS", "sector": "Telecom", "keywords": ["vodafone", "vi", "idea"]},
    {"name": "Tata Communications", "symbol": "TATACOMM.NS", "sector": "Telecom", "keywords": ["tata comm"]},

    # ── RETAIL & E-COMMERCE ───────────────────────────────────
    {"name": "Avenue Supermarts (DMart)", "symbol": "DMART.NS", "sector": "Retail", "keywords": ["dmart", "avenue supermarts"]},
    {"name": "Trent", "symbol": "TRENT.NS", "sector": "Retail", "keywords": ["trent", "westside", "zudio"]},
    {"name": "Shoppers Stop", "symbol": "SHOPERSTOP.NS", "sector": "Retail", "keywords": ["shoppers stop"]},

    # ── MEDIA & ENTERTAINMENT ─────────────────────────────────
    {"name": "Zee Entertainment", "symbol": "ZEEL.NS", "sector": "Media", "keywords": ["zee", "zee entertainment"]},
    {"name": "Sun TV Network", "symbol": "SUNTV.NS", "sector": "Media", "keywords": ["sun tv"]},
    {"name": "PVR INOX", "symbol": "PVRINOX.NS", "sector": "Media", "keywords": ["pvr", "inox", "pvr inox"]},

    # ── CHEMICALS ─────────────────────────────────────────────
    {"name": "Pidilite Industries", "symbol": "PIDILITIND.NS", "sector": "Chemicals", "keywords": ["pidilite", "fevicol"]},
    {"name": "SRF Limited", "symbol": "SRF.NS", "sector": "Chemicals", "keywords": ["srf"]},
    {"name": "Deepak Nitrite", "symbol": "DEEPAKNTR.NS", "sector": "Chemicals", "keywords": ["deepak nitrite"]},
    {"name": "Aarti Industries", "symbol": "AARTIIND.NS", "sector": "Chemicals", "keywords": ["aarti industries"]},
    {"name": "Navin Fluorine", "symbol": "NAVINFLUOR.NS", "sector": "Chemicals", "keywords": ["navin fluorine"]},
    {"name": "Vinati Organics", "symbol": "VINATIORGA.NS", "sector": "Chemicals", "keywords": ["vinati organics"]},

    # ── DEFENCE & AEROSPACE ───────────────────────────────────
    {"name": "Hindustan Aeronautics", "symbol": "HAL.NS", "sector": "Defence", "keywords": ["hal", "hindustan aeronautics"]},
    {"name": "Bharat Electronics", "symbol": "BEL.NS", "sector": "Defence", "keywords": ["bel", "bharat electronics"]},
    {"name": "Bharat Dynamics", "symbol": "BDL.NS", "sector": "Defence", "keywords": ["bdl", "bharat dynamics"]},
    {"name": "Mazagon Dock", "symbol": "MAZDOCK.NS", "sector": "Defence", "keywords": ["mazagon dock", "mdl"]},
    {"name": "Garden Reach Shipbuilders", "symbol": "GRSE.NS", "sector": "Defence", "keywords": ["grse", "garden reach"]},

    # ── AGRICULTURE & FERTILISERS ─────────────────────────────
    {"name": "UPL Limited", "symbol": "UPL.NS", "sector": "Agriculture", "keywords": ["upl", "united phosphorus"]},
    {"name": "Coromandel International", "symbol": "COROMANDEL.NS", "sector": "Fertiliser", "keywords": ["coromandel"]},
    {"name": "Chambal Fertilisers", "symbol": "CHAMBLFERT.NS", "sector": "Fertiliser", "keywords": ["chambal"]},
    {"name": "Bayer CropScience", "symbol": "BAYERCROP.NS", "sector": "Agriculture", "keywords": ["bayer crop"]},

    # ── NEW-AGE & FINTECH ─────────────────────────────────────
    {"name": "Paytm (One97 Communications)", "symbol": "PAYTM.NS", "sector": "Fintech", "keywords": ["paytm", "one97"]},
    {"name": "Nykaa (FSN E-Commerce)", "symbol": "NYKAA.NS", "sector": "E-Commerce", "keywords": ["nykaa", "fsn"]},
    {"name": "Zomato", "symbol": "ZOMATO.NS", "sector": "Food Tech", "keywords": ["zomato"]},
    {"name": "Policy Bazaar (PB Fintech)", "symbol": "POLICYBZR.NS", "sector": "Fintech", "keywords": ["policybazaar", "pb fintech"]},
    {"name": "Delhivery", "symbol": "DELHIVERY.NS", "sector": "Logistics", "keywords": ["delhivery"]},
    {"name": "CarTrade Tech", "symbol": "CARTRADE.NS", "sector": "Auto Tech", "keywords": ["cartrade"]},

    # ── LOGISTICS & SHIPPING ──────────────────────────────────
    {"name": "Container Corporation", "symbol": "CONCOR.NS", "sector": "Logistics", "keywords": ["concor", "container corp"]},
    {"name": "Blue Dart Express", "symbol": "BLUEDART.NS", "sector": "Logistics", "keywords": ["blue dart"]},
    {"name": "Gati Limited", "symbol": "GATI.NS", "sector": "Logistics", "keywords": ["gati"]},
    {"name": "Great Eastern Shipping", "symbol": "GESHIP.NS", "sector": "Shipping", "keywords": ["great eastern shipping"]},

    # ── COMMODITIES (traded on NSE) ───────────────────────────
    {"name": "Gold ETF (Nippon)", "symbol": "GOLDBEES.NS", "sector": "Commodity ETF", "keywords": ["gold etf", "gold", "goldbees"]},
    {"name": "Silver ETF (Nippon)", "symbol": "SILVERBEES.NS", "sector": "Commodity ETF", "keywords": ["silver etf", "silver", "silverbees"]},
    {"name": "Crude Oil ETF", "symbol": "OILIETF.NS", "sector": "Commodity ETF", "keywords": ["crude oil etf", "oil etf"]},
]

# ─────────────────────────────────────────────────────────────
# Build lookup structures
# ─────────────────────────────────────────────────────────────

def build_mapping():
    mapping = {
        "stocks": NSE_STOCKS,
        "by_symbol": {},
        "by_name_lower": {},
        "sectors": {}
    }

    for stock in NSE_STOCKS:
        sym = stock["symbol"]
        mapping["by_symbol"][sym] = stock

        # index by lowercase name
        name_lower = stock["name"].lower()
        mapping["by_name_lower"][name_lower] = sym

        # index each keyword
        for kw in stock.get("keywords", []):
            mapping["by_name_lower"][kw.lower()] = sym

        # group by sector
        sector = stock["sector"]
        if sector not in mapping["sectors"]:
            mapping["sectors"][sector] = []
        mapping["sectors"][sector].append(sym)

    return mapping


def main():
    mapping = build_mapping()

    # Save full mapping
    with open("nse_stocks.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    # Save simple list for frontend search autocomplete
    simple_list = [
        {"name": s["name"], "symbol": s["symbol"], "sector": s["sector"]}
        for s in NSE_STOCKS
    ]
    with open("nse_stocks_simple.json", "w", encoding="utf-8") as f:
        json.dump(simple_list, f, indent=2, ensure_ascii=False)

    print(f"Generated nse_stocks.json — {len(NSE_STOCKS)} stocks")
    print(f"Generated nse_stocks_simple.json — for frontend autocomplete")
    print(f"\nSectors covered:")
    sectors = {}
    for s in NSE_STOCKS:
        sectors[s["sector"]] = sectors.get(s["sector"], 0) + 1
    for sector, count in sorted(sectors.items()):
        print(f"  {sector}: {count} stocks")


if __name__ == "__main__":
    main()