import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# Page configuration for mobile viewports
st.set_page_config(page_title="Spready", page_icon="📈", layout="centered")

st.title("📈 Spready")
st.caption("ROIC - WACC Spread Screener & Tracker")

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

    ebit = financials.loc['EBIT'].iloc[0]
    try:
        pretax = financials.loc['Pretax Income'].iloc[0]
        tax_prov = financials.loc['Tax Provision'].iloc[0]
        tax_rate = tax_prov / pretax if pretax > 0 else 0.21
    except Exception:
        tax_rate = 0.21

    nopat = ebit * (1 - tax_rate)

    total_debt = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
    equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
    cash = balance_sheet.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in balance_sheet.index else 0

    invested_capital = total_debt + equity - cash
    if invested_capital <= 0:
        return None

    roic = nopat / invested_capital

    beta = info.get('beta')
    beta = float(beta) if beta is not None else 1.0
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
    
    if period == "Annual":
        fin = stock.financials
        bs = stock.balance_sheet
    else:
        fin = stock.quarterly_financials
        bs = stock.quarterly_balance_sheet
        
    if fin.empty or bs.empty:
        return pd.DataFrame()
        
    beta = info.get('beta')
    beta = float(beta) if beta is not None else 1.0
    market_return = 0.10
    cost_of_equity = rf_rate + beta * (market_return - rf_rate)
    
    records = []
    
    for date in fin.columns:
        try:
            if date not in bs.columns:
                continue
                
            ebit = fin.loc['EBIT', date] if 'EBIT' in fin.index else 0
            try:
                pretax = fin.loc['Pretax Income', date]
                tax_prov = fin.loc['Tax Provision', date]
                tax_rate = tax_prov / pretax if pretax > 0 else 0.21
            except:
                tax_rate = 0.21
                
            nopat = ebit * (1 - tax_rate)
            
            total_debt = bs.loc['Total Debt', date] if 'Total Debt' in bs.index else 0
            equity = bs.loc['Stockholders Equity', date] if 'Stockholders Equity' in bs.index else 0
            cash = bs.loc['Cash And Cash Equivalents', date] if 'Cash And Cash Equivalents' in bs.index else 0
            
            invested_capital = total_debt + equity - cash
            if invested_capital <= 0:
                continue
                
            roic = nopat / invested_capital
            if period == "Quarterly":
                roic = roic * 4  # Annualize 3-month ROIC for WACC comparison
                
            interest = fin.loc['Interest Expense', date] if 'Interest Expense' in fin.index else 0
            if period == "Quarterly":
                interest = interest * 4  # Annualize interest expense
                
            cost_of_debt = (interest / total_debt) if total_debt > 0 else 0.0
            
            market_cap = info.get('marketCap', equity)
            total_capital = market_cap + total_debt
            
            weight_eq = market_cap / total_capital if total_capital > 0 else 1.0
            weight_dt = total_debt / total_capital if total_capital > 0 else 0.0
            
            wacc = (weight_eq * cost_of_equity) + (weight_dt * cost_of_debt * (1 - tax_rate))
            spread = roic - wacc
            
            records.append({
                "Date": date.strftime('%Y-%m-%d'),
                "ROIC (%)": round(roic * 100, 2),
                "WACC (%)": round(wacc * 100, 2),
                "Spread (%)": round(spread * 100, 2)
            })
        except Exception:
            continue
            
    df_hist = pd.DataFrame(records)
    if not df_hist.empty:
        df_hist = df_hist.sort_values("Date").reset_index(drop=True)
    return df_hist

# Input Form
with st.form("screener_form"):
    ticker_input = st.text_input("Enter US Tickers (comma/space separated):", value="FAST, WSO, ENSG")
    submitted = st.form_submit_button("Run Analysis", use_container_width=True)

raw_tickers = ticker_input.replace(",", " ").split()
tickers = [t.upper().strip() for t in raw_tickers if t.strip()]

# Tab Layout
tab1, tab2 = st.tabs(["⚡ Instant Value", "📊 Trend Chart"])

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
                st.dataframe(
                    df.style.map(
                        lambda v: "color: #00c853; font-weight: bold;" if v > 0 else "color: #d50000; font-weight: bold;",
                        subset=["Spread (%)"]
                    ),
                    use_container_width=True, hide_index=True
                )
            if failed:
                st.caption(f"Data missing for: {', '.join(failed)}")

with tab2:
    if tickers:
        st.caption("Note: Free Yahoo Finance data is limited to the trailing 4 years (Annual) and 5 quarters (Quarterly).")
        col1, col2 = st.columns(2)
        with col1:
            selected_ticker = st.selectbox("Select Ticker for Charting", tickers)
        with col2:
            time_period = st.selectbox("Timeframe", ["Annual (Last 4 Yrs)", "Quarterly (Last 1 Yr)"])
            
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
