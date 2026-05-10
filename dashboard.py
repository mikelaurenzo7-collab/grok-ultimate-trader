import streamlit as st
import requests

st.title("Grok Ultimate Kalshi Trader Dashboard")

try:
    response = requests.get("http://localhost:8000/balance")
    data = response.json()
    st.metric("Current Balance", f"${data['balance']:.2f}")
    st.subheader("Top Opportunities")
    st.dataframe(data['opportunities'])
except:
    st.warning("Backend not running or demo mode")