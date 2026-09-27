import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# Page configuration for mobile viewports
st.set_page_config(page_title="Spready", page_icon="📈", layout="centered")

st.title("📈 Spready")
st.caption("ROIC - WACC Spread Screener & Tracker")

def style_spread(v):
    if isinstance(v, str) and v == "Infinite":
        return "color: #00c853; font-weight: bold;"
    if isinstance(v, (int, float)):
        return "color: #00c853; font-weight: bold;" if v > 0 else "color: #d50000; font-weight: bold;"
    return ""

@st.cache_data(ttl=3600)
def fetch_risk_free_rate():
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1]) / 100
    except Exception:
        pass
    return 0.045  # Standard fallback

@st.cache_data(ttl=1800)
def calculate_metrics(ticker_symbol, rf_rate, market_return=0.10):
    stock = yf.Ticker(ticker_symbol.strip())
    info = stock.info
    financials = stock.financials
    balance_sheet = stock.balance_sheet

    if financials.empty or balance_sheet.empty:
        return None

    ebit = financials.loc['EBIT'].iloc[0] if 'EBIT' in financials.index else 0
    try:
        pretax = financials.loc['Pretax Income'].iloc[0]
        tax_prov = financials.loc['Tax Provision'].iloc[0]
        tax_rate = tax_prov / pretax if pretax > 0 else 0.21
    except:
        tax_rate = 0.21

    nopat = ebit * (1 - tax_rate)

    total_debt = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
    equity = balance_sheet.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in balance_sheet.index else 0
    cash = balance_sheet.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in balance_sheet.index else 0

    invested_capital = total_debt + equity - cash
    if invested_capital <= 0: return None

    roic = nopat / invested_capital

    beta = float(info.get('beta', 1.0) or 1.0)
    cost_of_equity = rf_rate + beta * (market_return - rf_rate)

    interest = financials.loc['Interest Expense'].iloc[0] if 'Interest Expense' in financials.index else 0
    cost_of_debt = (interest / total_debt) if total_debt > 0 else 0.0

    market_cap = info.get('marketCap', equity)
    total_capital = market_cap + total_debt

    weight_eq = market_cap / total_capital if total_capital > 0 else 1.0
    weight_dt = total_debt / total_capital if total_capital > 0 else 0.0

    wacc = (weight_eq * cost_of_equity) + (weight_dt * cost_of_debt * (1 - tax_rate))
    spread = roic - wacc

    return {
        "Ticker": ticker_symbol.strip().upper(),
        "ROIC (%)": round(roic * 100, 2),
        "WACC (%)": round(wacc * 100, 2),
        "Spread (%)": round(spread * 100, 2)
    }

@st.cache_data(ttl=1800)
def calculate_historical_metrics(ticker_symbol, rf_rate, period="Annual"):
    stock = yf.Ticker(ticker_symbol.strip())
    info = stock.info
    fin = stock.financials if period == "Annual" else stock.quarterly_financials
    bs = stock.balance_sheet if period == "Annual" else stock.quarterly_balance_sheet
        
    if fin.empty or bs.empty: return pd.DataFrame()
        
    beta = float(info.get('beta', 1.0) or 1.0)
    market_return = 0.10
    cost_of_equity = rf_rate + beta * (market_return - rf_rate)
    records = []
    
    for date in fin.columns:
        try:
            if date not in bs.columns: continue
            ebit = fin.loc['EBIT', date] if 'EBIT' in fin.index else 0
            try:
                pretax = fin.loc['Pretax Income', date]
                tax_prov = fin.loc['Tax Provision', date]
                tax_rate = tax_prov / pretax if pretax > 0 else 0.21
            except: tax_rate = 0.21
                
            nopat = ebit * (1 - tax_rate)
            total_debt = bs.loc['Total Debt', date] if 'Total Debt' in bs.index else 0
            equity = bs.loc['Stockholders Equity', date] if 'Stockholders Equity' in bs.index else 0
            cash = bs.loc['Cash And Cash Equivalents', date] if 'Cash And Cash Equivalents' in bs.index else 0
            
            invested_capital = total_debt + equity - cash
            if invested_capital <= 0: continue
                
            roic = nopat / invested_capital
            if period == "Quarterly": roic = roic * 4  # Annualize
                
            interest = fin.loc['Interest Expense', date] if 'Interest Expense' in fin.index else 0
            if period == "Quarterly": interest = interest * 4  
                
            cost_of_debt = (interest / total_debt) if total_debt > 0 else 0.0
            market_cap = info.get('marketCap', equity)
            total_capital = market_cap + total_debt
            weight_eq = market_cap / total_capital if total_capital > 0 else 1.0
            weight_dt = total_debt / total_capital if total_capital > 0 else 0.0
            
            wacc = (weight_eq * cost_of_equity) + (weight_dt * cost_of_debt * (1 - tax_rate))
            spread = roic - wacc
            
            records.append({
                "Date": date.strftime('%Y-%m-%d'),
                "ROIC (%)": round(roic * 100, 2), "WACC (%)": round(wacc * 100, 2), "Spread (%)": round(spread * 100, 2)
            })
        except Exception: continue
            
    df_hist = pd.DataFrame(records)
    if not df_hist.empty: df_hist = df_hist.sort_values("Date").reset_index(drop=True)
    return df_hist

@st.cache_data(ttl=1800)
def calculate_rotce_metrics(ticker_symbol, rf_rate, market_return=0.10):
    stock = yf.Ticker(ticker_symbol.strip())
    info = stock.info
    fin = stock.financials
    bs = stock.balance_sheet
    cf = stock.cashflow

    if fin.empty or bs.empty: return None

    # 1. Numerator Adjustment: Find Amortization & Add to EBIT
    ebit = fin.loc['EBIT'].iloc[0] if 'EBIT' in fin.index else 0
    try:
        pretax = fin.loc['Pretax Income'].iloc[0]
        tax_prov = fin.loc['Tax Provision'].iloc[0]
        tax_rate = tax_prov / pretax if pretax > 0 else 0.21
    except: tax_rate = 0.21

    amortization = 0
    if not cf.empty:
        if 'Amortization' in cf.index and not pd.isna(cf.loc['Amortization'].iloc[0]):
            amortization = cf.loc['Amortization'].iloc[0]
        elif 'Amortization Of Intangibles' in cf.index and not pd.isna(cf.loc['Amortization Of Intangibles'].iloc[0]):
            amortization = cf.loc['Amortization Of Intangibles'].iloc[0]

    adj_ebit = ebit + amortization
    adj_nopat = adj_ebit * (1 - tax_rate)

    # 2. Denominator Adjustment: Strip Goodwill & Intangibles
    total_debt = bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0
    equity = bs.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in bs.index else 0
    cash = bs.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in bs.index else 0
    
    gw_int = 0
    if 'Goodwill And Other Intangible Assets' in bs.index and not pd.isna(bs.loc['Goodwill And Other Intangible Assets'].iloc[0]):
        gw_int = bs.loc['Goodwill And Other Intangible Assets'].iloc[0]
    else:
        gw = bs.loc['Goodwill'].iloc[0] if 'Goodwill' in bs.index and not pd.isna(bs.loc['Goodwill'].iloc[0]) else 0
        intan = bs.loc['Other Intangible Assets'].iloc[0] if 'Other Intangible Assets' in bs.index and not pd.isna(bs.loc['Other Intangible Assets'].iloc[0]) else 0
        gw_int = gw + intan

    tangible_ic = (total_debt + equity - cash) - gw_int
    
    if tangible_ic <= 0:
        rotce = np.nan # Tangible capital is negative/zero, meaning infinite returns
    else:
        rotce = adj_nopat / tangible_ic

    # 3. WACC Calculation (Standard)
    beta = float(info.get('beta', 1.0) or 1.0)
    cost_of_equity = rf_rate + beta * (market_return - rf_rate)
    interest = fin.loc['Interest Expense'].iloc[0] if 'Interest Expense' in fin.index else 0
    cost_of_debt = (interest / total_debt) if total_debt > 0 else 0.0
    
    market_cap = info.get('marketCap', equity)
    total_capital = market_cap + total_debt
    weight_eq = market_cap / total_capital if total_capital > 0 else 1.0
    weight_dt = total_debt / total_capital if total_capital > 0 else 0.0
    
    wacc = (weight_eq * cost_of_equity) + (weight_dt * cost_of_debt * (1 - tax_rate))
    spread = rotce - wacc if not pd.isna(rotce) else np.nan

    return {
        "Ticker": ticker_symbol.strip().upper(),
        "ROTCE (%)": round(rotce * 100, 2) if not pd.isna(rotce) else "Infinite",
        "WACC (%)": round(wacc * 100, 2),
        "Spread (%)": round(spread * 100, 2) if not pd.isna(spread) else "Infinite",
        "Intangibles Stripped": f"${gw_int / 1e9:.2f}B" if gw_int > 0 else "$0"
    }

# Input Form
with st.form("screener_form"):
    ticker_input = st.text_input("Enter US Tickers (comma/space separated):", value="FAST, APG, WSO, ENSG")
    submitted = st.form_submit_button("Run Analysis", use_container_width=True)

raw_tickers = ticker_input.replace(",", " ").split()
tickers = [t.upper().strip() for t in raw_tickers if t.strip()]

# UI Layout with 3 Tabs
tab1, tab2, tab3 = st.tabs(["⚡ Instant Value", "📊 Trend Chart", "🧩 Acquirers (ROTCE)"])

with tab1:
    if submitted or tickers:
        with st.spinner("Pulling latest filings..."):
            rf_rate = fetch_risk_free_rate()
            results, failed = [], []
            for sym in tickers:
                try:
                    res = calculate_metrics(sym, rf_rate)
                    if res: results.append(res)
                    else: failed.append(sym)
                except: failed.append(sym)
            
            if results:
                df = pd.DataFrame(results).sort_values(by="Spread (%)", ascending=False).reset_index(drop=True)
                st.dataframe(df.style.map(style_spread, subset=["Spread (%)"]), use_container_width=True, hide_index=True)
            if failed:
                st.caption(f"Data missing for: {', '.join(failed)}")

with tab2:
    if tickers:
        st.caption("Historical standard ROIC/WACC Trends")
        col1, col2 = st.columns(2)
        with col1: selected_ticker = st.selectbox("Select Ticker", tickers)
        with col2: time_period = st.selectbox("Timeframe", ["Annual (Last 4 Yrs)", "Quarterly (Last 1 Yr)"])
            
        period_arg = "Annual" if "Annual" in time_period else "Quarterly"
        
        if selected_ticker:
            with st.spinner(f"Fetching historical data for {selected_ticker}..."):
                rf_rate = fetch_risk_free_rate()
                df_hist = calculate_historical_metrics(selected_ticker, rf_rate, period_arg)
                if not df_hist.empty:
                    chart_data = df_hist.set_index("Date")
                    st.line_chart(chart_data, use_container_width=True)
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"Not enough historical data available for {selected_ticker}.")

with tab3:
    st.caption("Adjusts NOPAT by adding back Amortization and strips Goodwill/Intangibles from Capital to reveal actual cash-on-tangible-capital returns.")
    if submitted or tickers:
        with st.spinner("Calculating tangible returns..."):
            rf_rate = fetch_risk_free_rate()
            rotce_results, rotce_failed = [], []
            for sym in tickers:
                try:
                    res = calculate_rotce_metrics(sym, rf_rate)
                    if res: rotce_results.append(res)
                    else: rotce_failed.append(sym)
                except: rotce_failed.append(sym)
            
            if rotce_results:
                df_rotce = pd.DataFrame(rotce_results)
                # Sort numerically, handling "Infinite" strings properly
                df_rotce['Sort_Key'] = pd.to_numeric(df_rotce['Spread (%)'], errors='coerce').fillna(999999)
                df_rotce = df_rotce.sort_values(by="Sort_Key", ascending=False).drop(columns=['Sort_Key']).reset_index(drop=True)
                
                st.dataframe(df_rotce.style.map(style_spread, subset=["Spread (%)"]), use_container_width=True, hide_index=True)
            if rotce_failed:
                st.caption(f"Could not calculate ROTCE for: {', '.join(rotce_failed)}")
