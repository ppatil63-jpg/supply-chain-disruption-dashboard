import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from math import sqrt
import xml.etree.ElementTree as ET
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title='SC Disruption Dashboard', layout='wide', page_icon='⚠')
st.title('🌍 Natural Supply Chain Disruption Prediction Dashboard')
st.caption(f"Live: USGS Earthquakes | GDACS Disasters | Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

@st.cache_data(ttl=3600)
def get_quakes():
    try:
        p = {'format':'geojson','starttime':(datetime.utcnow()-timedelta(days=7)).strftime('%Y-%m-%d'),'minmagnitude':4.5,'orderby':'magnitude'}
        feats = requests.get('https://earthquake.usgs.gov/fdsnws/event/1/query',params=p,timeout=15).json()['features']
        return pd.DataFrame([{'event':f['properties'].get('title'),'lat':f['geometry']['coordinates'][1],'lon':f['geometry']['coordinates'][0],'magnitude':f['properties'].get('mag'),'place':f['properties'].get('place')} for f in feats])
    except Exception as e:
        st.warning(f'Earthquake data error: {e}')
        return pd.DataFrame(columns=['event','lat','lon','magnitude','place'])

@st.cache_data(ttl=3600)
def get_gdacs():
    try:
        root = ET.fromstring(requests.get('https://www.gdacs.org/xml/rss.xml',timeout=15).content)
        rows = []
        for item in root.iter('item'):
            el = item.find('{http://www.georss.org/georss}point')
            if el is not None:
                lat, lon = map(float, el.text.strip().split())
                rows.append({'event': item.findtext('title') or '', 'lat': lat, 'lon': lon})
        return pd.DataFrame(rows)
    except Exception as e:
        st.warning(f'GDACS data error: {e}')
        return pd.DataFrame(columns=['event','lat','lon'])

REGIONS = [
    {'name':'Middle East/Persian Gulf','lat':26.0,'lon':50.5,'r':12,'impact':'Oil & LNG, Shipping lanes','base':80},
    {'name':'Strait of Hormuz','lat':26.5,'lon':56.5,'r':4,'impact':'20pct global oil transit','base':75},
    {'name':'Suez Canal Corridor','lat':30.5,'lon':32.3,'r':5,'impact':'12pct global trade','base':65},
    {'name':'Taiwan Strait','lat':24.5,'lon':119.5,'r':5,'impact':'Semiconductors, electronics','base':60},
    {'name':'Eastern Europe/Black Sea','lat':47.5,'lon':34.0,'r':10,'impact':'Grain, Fertilizer, Steel','base':70},
    {'name':'SE Asia/Malacca Strait','lat':2.5,'lon':103.5,'r':8,'impact':'Container routes, Palm oil','base':40},
    {'name':'West Africa','lat':5.5,'lon':2.5,'r':12,'impact':'Cocoa, Critical minerals, Oil','base':55},
    {'name':'S America Pacific Coast','lat':-20.0,'lon':-70.0,'r':12,'impact':'Copper, Lithium, Soybeans','base':35},
    {'name':'Japan / Korea','lat':36.0,'lon':128.0,'r':8,'impact':'Auto parts, Electronics','base':30},
    {'name':'Indian Subcontinent','lat':20.0,'lon':77.0,'r':12,'impact':'Textiles, Pharma, IT','base':30},
    {'name':'US Gulf Coast','lat':28.5,'lon':-90.5,'r':8,'impact':'Oil refining, Petrochemicals','base':25},
    {'name':'Panama Canal','lat':9.0,'lon':-79.5,'r':3,'impact':'Asia-US container route','base':30},
]

def dist(a,b,c,d): return sqrt((a-c)**2+(b-d)**2)

def score_regions(dq, dg):
    rows = []
    for reg in REGIONS:
        r = reg['r']
        nq = dq[dq.apply(lambda x: dist(x.lat,x.lon,reg['lat'],reg['lon']) <= r, axis=1)] if not dq.empty else pd.DataFrame()
        ng = dg[dg.apply(lambda x: dist(x.lat,x.lon,reg['lat'],reg['lon']) <= r, axis=1)] if not dg.empty else pd.DataFrame()
        qs = min(nq['magnitude'].sum()*3, 40) if not nq.empty else 0
        gs = min(len(ng)*10, 30)
        total = min(round(reg['base']*0.40 + qs*0.30 + gs*0.20, 1), 100)
        lvl = 'CRITICAL' if total>=70 else 'HIGH' if total>=50 else 'MEDIUM' if total>=30 else 'LOW'
        clr = '#FF0000' if lvl=='CRITICAL' else '#FF8C00' if lvl=='HIGH' else '#FFD700' if lvl=='MEDIUM' else '#00CC44'
        rows.append({'Region':reg['name'],'lat':reg['lat'],'lon':reg['lon'],'Risk Score':total,'Level':lvl,'Color':clr,'Trade Impact':reg['impact'],'EQ':len(nq),'Disasters':len(ng)})
    return pd.DataFrame(rows).sort_values('Risk Score', ascending=False).reset_index(drop=True)

with st.spinner('Fetching live global data...'):
    dq = get_quakes()
    dg = get_gdacs()
    dr = score_regions(dq, dg)

c1,c2,c3,c4 = st.columns(4)
c1.metric('Critical Regions', len(dr[dr['Level']=='CRITICAL']))
c2.metric('High Risk Regions', len(dr[dr['Level']=='HIGH']))
c3.metric('Earthquakes (7d)', len(dq), f"Max M{dq['magnitude'].max():.1f}" if not dq.empty else 'N/A')
c4.metric('GDACS Disasters', len(dg))
st.divider()

tab1, tab2, tab3 = st.tabs(['Risk Map', 'Charts', 'Data Tables'])

with tab1:
    st.subheader('Global Supply Chain Risk Map')
    m = folium.Map(location=[20, 0], zoom_start=2, tiles='CartoDB dark_matter')
    for _, row in dr.iterrows():
        folium.Circle(location=[row['lat'], row['lon']],radius=int(row['Risk Score']*6000),color=row['Color'],fill=True,fill_opacity=0.3,tooltip=f"{row['Region']}: {row['Level']} ({row['Risk Score']})",popup=f"**{row['Region']}**\nScore: {row['Risk Score']}/100\nTrade: {row['Trade Impact']}\nEQ:{row['EQ']} Disasters:{row['Disasters']}").add_to(m)
    eq_fg = folium.FeatureGroup('Earthquakes USGS', show=True)
    for _, row in dq.iterrows():
        mag = row.get('magnitude', 0) or 0
        c = 'red' if mag >= 6.5 else 'orange' if mag >= 5.5 else 'yellow'
        folium.CircleMarker([row['lat'], row['lon']], radius=max(3, mag*1.5), color=c, fill=True, fill_opacity=0.7, tooltip=f"M{mag} - {row.get('place','')}").add_to(eq_fg)
    eq_fg.add_to(m)
    gdacs_fg = folium.FeatureGroup('GDACS Disasters', show=True)
    for _, row in dg.iterrows():
        folium.Marker([row['lat'], row['lon']], icon=folium.Icon(color='purple', icon='exclamation-sign', prefix='glyphicon'), tooltip=str(row.get('event',''))[:80]).add_to(gdacs_fg)
    gdacs_fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, height=500, use_container_width=True)

with tab2:
    st.subheader('Risk Score Analysis')
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Risk Score by Region', 'Risk Level Distribution'), column_widths=[0.65, 0.35], specs=[[{'type':'bar'},{'type':'pie'}]])
    fig.add_trace(go.Bar(x=dr['Risk Score'], y=dr['Region'], orientation='h', marker_color=dr['Color'], text=dr['Level'], textposition='inside'), row=1, col=1)
    lc = dr['Level'].value_counts()
    clr_map = {'CRITICAL':'#FF0000','HIGH':'#FF8C00','MEDIUM':'#FFD700','LOW':'#00CC44'}
    fig.add_trace(go.Pie(labels=lc.index, values=lc.values, marker_colors=[clr_map.get(l,'grey') for l in lc.index], hole=0.45, textinfo='label+percent'), row=1, col=2)
    fig.update_layout(paper_bgcolor='#0d0d1a', plot_bgcolor='#0d0d1a', font_color='white', height=520, showlegend=False, title_text='Supply Chain Disruption Risk Dashboard')
    fig.update_xaxes(range=[0,100], row=1, col=1, gridcolor='#333')
    fig.update_yaxes(row=1, col=1, tickfont=dict(size=9))
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader('Risk Scores by Region')
    st.dataframe(dr[['Region','Risk Score','Level','Trade Impact','EQ','Disasters']].rename(columns={'EQ':'Earthquakes'}), use_container_width=True)
    st.subheader('Recent Earthquakes (USGS - Last 7 Days)')
    st.dataframe(dq.head(25), use_container_width=True)
    st.subheader('GDACS Natural Disaster Alerts')
    st.dataframe(dg.head(25), use_container_width=True)

st.sidebar.title('About This Dashboard')
st.sidebar.info('Predicts natural supply chain disruptions using:\n- USGS Earthquake API\n- GDACS Global Disaster Alerts\n\nRefreshes every hour.')
st.sidebar.markdown('Built for: Supply Chain Analytics Portfolio')
