import streamlit as st
from PIL import Image
import pandas as pd
import os
import googlemaps
import pydeck as pdk
from geopy.distance import geodesic
from streamlit_geolocation import streamlit_geolocation
import numpy as np

# ==================================================
# UI STYLE
# ==================================================
st.set_page_config(layout="wide", page_title="DOIDOI")

# ==================================================
# UI STYLE (動的コンパス)
# ==================================================
if "map_bearing" not in st.session_state:
    st.session_state.map_bearing = 0

def render_compass(bearing):
    rotation = -bearing 
    st.markdown(f"""
    <style>
    .main {{ background-color: #FFFBF0; }}
    [data-testid="stHeader"] {{ background-color: #FFFBF0; }}
    .compass-container {{
        position: fixed;
        bottom: 40px;
        right: 40px;
        z-index: 1000;
        width: 100px;
        height: 100px;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
    }}
    .compass-wrapper {{
        position: relative;
        width: 70px;
        height: 70px;
        transform: rotate({rotation}deg);
        transition: transform 0.3s ease-out;
    }}
    .direction {{
        position: absolute;
        font-weight: bold;
        font-size: 14px;
        color: #d32f2f;
        background: rgba(255,255,255,0.8);
        padding: 1px 4px;
        border-radius: 4px;
        line-height: 1;
    }}
    .n {{ top: -22px; left: 50%; transform: translateX(-50%); color: #d32f2f; }}
    .s {{ bottom: -22px; left: 50%; transform: translateX(-50%); color: #333; }}
    .e {{ right: -22px; top: 50%; transform: translateY(-50%); color: #333; }}
    .w {{ left: -22px; top: 50%; transform: translateY(-50%); color: #333; }}
    </style>
    <div class="compass-container">
        <div class="compass-wrapper">
            <div class="direction n">N</div>
            <div class="direction s">S</div>
            <div class="direction e">E</div>
            <div class="direction w">W</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

render_compass(st.session_state.map_bearing)

# ==================================================
# Google Maps API
# ==================================================
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
gmaps = googlemaps.Client(key=API_KEY)

# ==================================================
# Utility
# ==================================================
def geocode_location(text):
    try:
        results = gmaps.geocode(text, language="ja")
        if not results:
            return None
        loc = results[0]
        return {
            'lat': loc['geometry']['location']['lat'],
            'lon': loc['geometry']['location']['lng']
        }
    except:
        return None

def load_spot_data(file_name):
    df = pd.read_excel(file_name)
    df.columns = df.columns.str.strip()
    df = df.rename(columns={'latitude': 'lat', 'longitude': 'lon', '緯度': 'lat', '経度': 'lon'})
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['Review_time'] = df['Review_time'].astype(str)
    df = df.dropna(subset=['lat', 'lon'])
    df = df.sort_values(by=['Rating', 'Review_time'], ascending=[False, False])
    df = df.drop_duplicates(subset=['Name'], keep='first')
    return df

def load_review_image(naming_value):
    base_path = "images"
    if not naming_value or str(naming_value) == "nan":
        return None
    target_filename = f"{str(naming_value).strip()}.jpg"
    full_path = os.path.join(base_path, target_filename)
    if os.path.exists(full_path):
        return Image.open(full_path)
    return None

# ==================================================
# Session State
# ==================================================
if "search" not in st.session_state:
    st.session_state.search = False
if "selected_spot" not in st.session_state:
    st.session_state.selected_spot = None
if "spots" not in st.session_state:
    st.session_state.spots = []

# ==================================================
# UI: Input
# ==================================================
st.title("🗺️ DOIDOI")
destination_text = st.text_input("🎯 目的地を入力")
detour_time = st.number_input("⏳ 寄り道可能時間（分）", 5, 180, 30)
location = streamlit_geolocation()

# ==================================================
# 検索処理 (ボタン押下時)
# ==================================================
if st.button("🔍 寄り道を探す"):
    if not location or not location.get("latitude"):
        st.warning("位置情報を取得してください")
        st.stop()
    geo = geocode_location(destination_text)
    if not geo:
        st.error("目的地が見つかりません")
        st.stop()
    user_lat, user_lon = float(location["latitude"]), float(location["longitude"])
    dest_lat, dest_lon = float(geo["lat"]), float(geo["lon"])
    st.session_state.user = {'lat': user_lat, 'lon': user_lon}
    st.session_state.destination = {'lat': dest_lat, 'lon': dest_lon}
    STAY_TIME_SEC = 10 * 60 
    df = load_spot_data("摂津富田駅_2km_2026.xlsx")
    results = []
    out_of_range = []
    for _, row in df.iterrows():
        try:
            r1 = gmaps.directions((user_lat, user_lon), (row['lat'], row['lon']), mode="walking")
            r2 = gmaps.directions((row['lat'], row['lon']), (dest_lat, dest_lon), mode="walking")
            if r1 and r2:
                d1_m = r1[0]['legs'][0]['distance']['value']
                d2_m = r2[0]['legs'][0]['distance']['value']
                t1_s = r1[0]['legs'][0]['duration']['value']
                t2_s = r2[0]['legs'][0]['duration']['value']
                total_dist_km = (d1_m + d2_m) / 1000.0
                total_dur_sec = t1_s + t2_s + STAY_TIME_SEC
                total_dur_min = total_dur_sec // 60
                spot_data = {
                    'Name': row['Name'], 'lat': row['lat'], 'lon': row['lon'],
                    'impression': str(row.get('impression vocabulary', '')),
                    'Catchphrase': str(row.get('Catchphrase', '')),
                    'naming': str(row.get('naming', '')),
                    'total_dist': total_dist_km, 'total_time': total_dur_min
                }
                if total_dur_sec <= detour_time * 60:
                    spot_data['label'] = f"{len(results) + 1}. {spot_data['impression']}"
                    results.append(spot_data)
                else:
                    spot_data['label'] = f"外{len(out_of_range) + 1}. {spot_data['impression']}"
                    out_of_range.append(spot_data)
        except:
            continue
    st.session_state.spots = results
    st.session_state.out_spots = out_of_range
    st.session_state.search = True
    st.session_state.selected_spot = None

# ==================================================
# 結果表示
# ==================================================
if st.session_state.search:
    user = st.session_state.user
    dest = st.session_state.destination
    spots = st.session_state.spots
    out_spots = st.session_state.get('out_spots', [])

    if st.session_state.selected_spot:
        s = st.session_state.selected_spot
        
        if st.button("🔙 リストに戻る"):
            st.session_state.selected_spot = None
            st.rerun()

        # 基本情報の提示（キャッチコピーと写真）
        st.title(f"📍 {s['Name']}")
        st.subheader(f"✨ {s.get('Catchphrase', '特別な寄り道が見つかりました')}")
        
        review_img = load_review_image(s['naming']) 
        if review_img:
            st.image(review_img, use_container_width=True)
        else:
            st.info("画像は準備中です。")

        st.markdown("---")

        # 距離の判定（徒歩距離）
        try:
            dist_res = gmaps.distance_matrix((user['lat'], user['lon']), (s['lat'], s['lon']), mode="walking")
            walking_dist_m = dist_res['rows'][0]['elements'][0]['distance']['value']
        except:
            walking_dist_m = 9999

        # 700m以内なら地図と経路を表示
        if walking_dist_m <= 3000:
            st.success(f"🗺️ スポットまで残り {walking_dist_m}m です。詳細な経路を表示します。")
            
            # 詳細経路の取得
            directions_res = gmaps.directions((user['lat'], user['lon']), (dest['lat'], dest['lon']), waypoints=[(s['lat'], s['lon'])], mode="walking")
            if directions_res:
                path_coords = []
                for leg in directions_res[0]['legs']:
                    for step in leg['steps']:
                        path_coords.append([step['start_location']['lng'], step['start_location']['lat']])
                    path_coords.append([leg['end_location']['lng'], leg['end_location']['lat']])
                
                path_df = pd.DataFrame([{"path": path_coords}])
                
                ICON_SPOT = {
                    "url": "https://4.bp.blogspot.com/-xz7m7yMI-CI/U1T3vVaFfZI/AAAAAAAAfWI/TOJPmuapl-c/s800/figure_standing.png",
                    "width": 250,
                    "height": 250,
                    "anchorY": 250
                }

                # アイコン用データ（データ構造をIconLayer用に変更）
                icon_data = [
                    # 現在地（青い点はそのまま維持、ScatterplotLayerで使用）
                    {'lat': user['lat'], 'lon': user['lon'], 'type': '現在地'},
                    # スポット（アイコンに変換、IconLayerで使用）
                    {'lat': s['lat'], 'lon': s['lon'], 'type': 'スポット', 'icon_data': ICON_SPOT}
                ]
                df_icons = pd.DataFrame(icon_data)

                st.pydeck_chart(pdk.Deck(
                    initial_view_state=pdk.ViewState(latitude=s['lat'], longitude=s['lon'], zoom=16, pitch=45),
                    layers=[
                        
                        # ② 現在地の青い点 (ScatterplotLayer) - スポットを除外し、現在地のみに
                        pdk.Layer(
                            "ScatterplotLayer",
                            df_icons[df_icons['type'] == '現在地'], # 現在地のみフィルタ
                            get_position='[lon, lat]',
                            get_fill_color=[0, 0, 255], # 青色固定
                            get_radius=15
                        ),
                        
                        # ③ 【追加】スポットのアイコン (IconLayer) - ここで赤い点をアイコンに置き換え
                        pdk.Layer(
                            "IconLayer",
                            df_icons[df_icons['type'] == 'スポット'], # スポットのみフィルタ
                            get_icon="icon_data",
                            get_size=4,
                            size_scale=10,
                            get_position="[lon, lat]"
                        ),
                        
                        # ④ 文字ラベル (TextLayer) - 変更なし
                        pdk.Layer("TextLayer", df_icons, get_position='[lon, lat]', get_text='type', get_size=20, get_pixel_offset=[0, -30])
                    ]
                ))
        else:
            st.warning(f"🔒 地図はまだ表示できません。あと {walking_dist_m - 3000}m ほど近づいてみてください。")

    else:
        # メインリスト表示
        center_lat, center_lon = (user['lat'] + dest['lat']) / 2, (user['lon'] + dest['lon']) / 2
        st.session_state.map_bearing = st.slider("地図の向き（角度）を調整", 0, 360, st.session_state.map_bearing)

        df_ok, df_ng = pd.DataFrame(spots), pd.DataFrame(out_spots)
        ICON_USER = {"url": "https://4.bp.blogspot.com/-xz7m7yMI-CI/U1T3vVaFfZI/AAAAAAAAfWI/TOJPmuapl-c/s800/figure_standing.png", "width": 250, "height": 250, "anchorY": 250}
        ICON_DEST = {"url": "https://png.pngtree.com/png-vector/20220630/ourmid/pngtree-location-activity-beach-collection-destination-png-image_5573458.png", "width": 250, "height": 250, "anchorY": 250}
        df_icons = pd.DataFrame([
            {'lat': user['lat'], 'lon': user['lon'], 'icon_data': ICON_USER}, 
            {'lat': dest['lat'], 'lon': dest['lon'], 'icon_data': ICON_DEST}
        ])


        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v10',
            initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=14, bearing=st.session_state.map_bearing),
            layers=[
                pdk.Layer("ScatterplotLayer", df_ng, get_position='[lon, lat]', get_fill_color=[150, 150, 150, 150], get_radius=30),
                pdk.Layer("ScatterplotLayer", df_ok, get_position='[lon, lat]', get_fill_color=[0, 200, 0], get_radius=40),
                pdk.Layer("TextLayer", pd.concat([df_ok, df_ng]) if not df_ng.empty else df_ok, get_position='[lon, lat]', get_text='label', get_size=18),
                pdk.Layer("IconLayer", df_icons, get_icon="icon_data", get_size=4, size_scale=10, get_position="[lon, lat]"),
                pdk.Layer("TextLayer", df_icons, get_position='[lon,lat]', get_text='text', get_size=25, get_pixel_offset=[0,-45])
            ]
        ))

        st.subheader(f"✅ 寄り道可能 ({len(spots)}件)")
        if spots:
            for i in range(0, len(spots), 2):
                cols = st.columns(2)
                for j in range(2):
                    if i + j < len(spots):
                        with cols[j]:
                            s = spots[i+j]
                            st.markdown(f"**{s['label']}**")
                            st.caption(f"🚶‍♂️ 約{s['total_dist']:.1f}km / 合計{s['total_time']}分")
                            if st.button("詳細を見る", key=f"list_btn_{s['label']}"):
                                st.session_state.selected_spot = s
                                st.rerun()
        
        st.markdown("---")
        st.subheader(f"❌ 寄り道不可能（時間外）({len(out_spots)}件)")
        if out_spots:
            for i in range(0, len(out_spots), 2):
                cols_out = st.columns(2)
                for j in range(2):
                    if i + j < len(out_spots):
                        with cols_out[j]:
                            s = out_spots[i+j]
                            st.markdown(f"**{s['label']}**")
                            st.caption(f"🚶‍♂️ 約{s['total_dist']:.1f}km / 合計{s['total_time']}分")
                            if st.button("詳細を見る", key=f"out_btn_{s['label']}"):
                                st.session_state.selected_spot = s
                                st.rerun()


