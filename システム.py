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

st.markdown("""
<style>
.main { background-color: #FFFBF0; }
[data-testid="stHeader"] { background-color: #FFFBF0; }
</style>
""", unsafe_allow_html=True)

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

    df = df.rename(columns={
        'latitude': 'lat',
        'longitude': 'lon',
        '緯度': 'lat',
        '経度': 'lon'
    })

    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0)
    df['Review_time'] = df['Review_time'].astype(str)

    df = df.dropna(subset=['lat', 'lon'])

    # Rating優先 → Review_time優先
    df = df.sort_values(by=['Rating', 'Review_time'], ascending=[False, False])
    df = df.drop_duplicates(subset=['Name'], keep='first')

    return df


def load_review_image(naming_value):
    # プログラムがある場所（ルート）
    base_path = os.path.dirname(__file__)
    
    if not naming_value or str(naming_value) == "nan":
        return None

    target_filename = f"{str(naming_value).strip()}.jpg"

    # --- 探す場所のリスト ---
    # 1. imagesフォルダの中 (今のGitHubの構成)
    # 2. images/images フォルダの中 (さっきまでなっていた構成)
    # 3. システム.pyと同じ場所 (画像が外に出てしまっている場合)
    possible_paths = [
        os.path.join(base_path, "images", target_filename),
        os.path.join(base_path, "images", "images", target_filename),
        os.path.join(base_path, target_filename)
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return Image.open(path)
    
    # どこにもなかった場合、画面にエラーを出して原因を突き止める
    st.error(f"⚠️ 画像が見つかりません: {target_filename}")
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

STAY_TIME_MIN = 15

location = streamlit_geolocation()

# ==================================================
# 検索処理 (ボタン押下時)
# ==================================================
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

    # ここで df を定義
    df = load_spot_data("摂津富田駅_2km_2026.xlsx")

    # --- ここから下の処理をすべて右にズラして、if の中に入れる ---
    results = []
    out_of_range = []

    for _, row in df.iterrows():
        try:
            r1 = gmaps.directions((user_lat, user_lon), (row['lat'], row['lon']), mode="walking")
            r2 = gmaps.directions((row['lat'], row['lon']), (dest_lat, dest_lon), mode="walking")

            if r1 and r2:
                total_dur = r1[0]['legs'][0]['duration']['value'] + r2[0]['legs'][0]['duration']['value'] + STAY_TIME_SEC
                
                spot_data = {
                    'Name': row['Name'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'impression': str(row.get('impression vocabulary', '')),
                    'Catchphrase': str(row.get('Catchphrase', '')),
                    'naming': str(row.get('naming', ''))
                }

                if total_dur <= detour_time * 60:
                    spot_data['label'] = f"{len(results) + 1}. {spot_data['impression']}"
                    spot_data['display_text'] = row['Name']
                    results.append(spot_data)
                else:
                    spot_data['label'] = f"外{len(out_of_range) + 1}. {spot_data['impression']}"
                    spot_data['display_text'] = f"範囲外 {row['Name']}"
                    out_of_range.append(spot_data)
        except:
            continue

    st.session_state.spots = results
    st.session_state.out_spots = out_of_range
    st.session_state.search = True
    st.session_state.selected_spot = None
    # --- ここまでを if の中に入れる ---

# ==================================================
# 結果表示
# ==================================================
if st.session_state.search:
    user = st.session_state.user
    dest = st.session_state.destination
    spots = st.session_state.spots
    out_spots = st.session_state.get('out_spots', [])

    # --- 135行目付近、詳細画面の表示 ---
    if st.session_state.selected_spot:
        s = st.session_state.selected_spot
        
        if st.button("🔙 リストに戻る"):
            st.session_state.selected_spot = None
            st.rerun()

        st.title(f"{s['Name']}")
        # st.subheader(f"✨ {s['impression']}")
        st.subheader(f"キャッチコピー: {s.get('Catchphrase', 'なし')}")

        
        # ★ ここを naming を使うように変更
        review_img = load_review_image(s['naming']) 
        
        if review_img:
            st.image(review_img, use_container_width=True)
        
        # 本来の画像読み込み用ラベル（数字部分のみなど）が必要な場合は調整が必要ですが、
        # ここでは元のロジックを維持し、s['label']を使用します。
        # review_img = load_review_image(s['naming']) 
        # if review_img:
        #     st.image(review_img, use_container_width=True)
        # else:
        #     st.warning("画像が見つかりませんでした")
            
    # --- リスト画面の表示 ---
    else:
        # 地図の計算
        center_lat = (user['lat'] + dest['lat']) / 2
        center_lon = (user['lon'] + dest['lon']) / 2
        radius_meters = (detour_time * 80) / 2 + 100

        df_ok = pd.DataFrame(spots)
        df_ng = pd.DataFrame(out_spots)
        
        # --- アイコン画像の設定 ---
        ICON_USER = {
            "url": "https://4.bp.blogspot.com/-xz7m7yMI-CI/U1T3vVaFfZI/AAAAAAAAfWI/TOJPmuapl-c/s800/figure_standing.png", 
            "width": 250, "height": 250, "anchorY": 250
        }
        ICON_DEST = {
            "url": "https://png.pngtree.com/png-vector/20220630/ourmid/pngtree-location-activity-beach-collection-destination-png-image_5573458.png",
            "width": 250, "height": 250, "anchorY": 250
        }

        icon_data = [
            {'lat': user['lat'], 'lon': user['lon'], 'icon_data': ICON_USER, 'text': '現在地'},
            {'lat': dest['lat'], 'lon': dest['lon'], 'icon_data': ICON_DEST, 'text': '目的地'}
        ]
        df_icons_img = pd.DataFrame(icon_data)

        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v10',
            initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=14),
            layers=[
                # 寄り道許容範囲の円
                pdk.Layer("ScatterplotLayer", data=[{'lat': center_lat, 'lon': center_lon}], get_position='[lon, lat]', get_radius=radius_meters, get_fill_color=[0, 255, 0, 30], pickable=False),
                # 寄り道不可スポット
                pdk.Layer("ScatterplotLayer", df_ng, get_position='[lon, lat]', get_fill_color=[150, 150, 150, 150], get_radius=30),
                # 寄り道可スポット
                pdk.Layer("ScatterplotLayer", df_ok, get_position='[lon, lat]', get_fill_color=[0, 200, 0], get_radius=40),
                # スポットのラベル（impression vocabularyを表示）
                pdk.Layer("TextLayer", pd.concat([df_ok, df_ng]) if not df_ng.empty else df_ok, get_position='[lon, lat]', get_text='label', get_size=18, get_color=[50, 50, 50]),
                
                # ★ 現在地と目的地の画像アイコン
                pdk.Layer(
                    "IconLayer",
                    df_icons_img,
                    get_icon="icon_data",
                    get_size=4,
                    size_scale=10,
                    get_position="[lon, lat]",
                    pickable=True,
                ),
                # 現在地・目的地の文字ラベル
                pdk.Layer(
                    "TextLayer",
                    df_icons_img,
                    get_position='[lon,lat]',
                    get_text='text',
                    get_size=25,
                    get_color=[0,0,0],
                    get_pixel_offset=[0,-45]
                )
            ]
        ))

        st.subheader(f"✅ 寄り道可能 ({len(spots)}件)")
        if spots:
            cols = st.columns(2)
            for i, s in enumerate(spots):
                with cols[i % 2]:
                    # リスト表示も「形容詞」を含める
                    st.markdown(f"{s['label']} ")
                    if st.button("詳細を見る", key=f"list_btn_{s['label']}"):
                        st.session_state.selected_spot = s
                        st.rerun()
        else:
            st.write("該当なし")

        st.markdown("---")

        st.subheader(f"❌ 寄り道不可能（時間外）({len(out_spots)}件)")
        if out_spots:
            cols_out = st.columns(2)
            for i, s in enumerate(out_spots):
                with cols_out[i % 2]:
                    st.markdown(f"{s['label']} ")
                    if st.button("詳細を見る", key=f"out_btn_{s['label']}"):
                        st.session_state.selected_spot = s

                        st.rerun()
