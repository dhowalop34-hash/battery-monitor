from datetime import datetime
import pandas as pd
from supabase import create_client, Client
import streamlit as st

# Настройки подключения к Supabase берутся из секретов Streamlit
@st.cache_resource
def init_supabase() -> Client:
  url = st.secrets["SUPABASE_URL"]
  key = st.secrets["SUPABASE_KEY"]
  return create_client(url, key)


supabase = init_supabase()


def agm_voltage_to_percentage(v):
  """Точный расчет процента заряда для 12V AGM"""
  if v >= 12.75:
    return 100.0
  if v <= 10.50:
    return 0.0

  table = [
      (12.75, 100.0),
      (12.50, 75.0),
      (12.30, 50.0),
      (12.00, 30.0),
      (11.60, 10.0),
      (10.50, 0.0),
  ]

  for i in range(len(table) - 1):
    v_high, p_high = table[i]
    v_low, p_low = table[i + 1]

    if v <= v_high and v >= v_low:
      p = p_low + (v - v_low) * (p_high - p_low) / (v_high - v_low)
      return round(p, 1)

  return 0.0


def get_status_color(voltage):
  """Возвращает статус и цвет по вольтажу"""
  if voltage >= 12.5:
    return "🟢 Норма", "green"
  elif voltage >= 12.3:
    return "🟠 Скоро заряжать", "orange"
  elif voltage >= 12.0:
    return "🔴 12V — Пора заряжать!", "red"
  else:
    return "⚫ Ниже 12V — Пиздец!", "black"


# Настройка страницы
st.set_page_config(
    page_title="Мониторинг АКБ",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔋 Мониторинг всех аккумуляторов")

# --- ПОЛУЧЕНИЕ СПИСКА АККУМУЛЯТОРОВ ---
batteries_res = (
    supabase.table("batteries").select("*").order("id", desc=False).execute()
)
batteries_df = pd.DataFrame(batteries_res.data)

# --- БОКОВАЯ ПАНЕЛЬ (Sidebar) ---
with st.sidebar:
  st.header("📝 Новый замер")

  battery_ids = (
      batteries_df["id"].tolist() if not batteries_df.empty else [1, 2, 3, 4]
  )

  with st.form(key="voltage_form"):
    selected_batt = st.selectbox(
        "Выберите АКБ:",
        battery_ids,
        format_func=lambda x: (
            f"АКБ №{x} ({batteries_df[batteries_df['id'] == x]['capacity'].values[0]} Ah)"
            if not batteries_df.empty
            else f"АКБ №{x}"
        ),
    )
    new_voltage = st.number_input(
        "Вольтаж (V):",
        min_value=0.0,
        max_value=20.0,
        value=12.7,
        step=0.01,
        format="%.2f",
    )
    submit_button = st.form_submit_button(
        label="💾 Сохранить замер", use_container_width=True
    )

    if submit_button:
      current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      calc_percentage = agm_voltage_to_percentage(new_voltage)

      # Вставка замера в Supabase
      supabase.table("history").insert({
          "battery_id": selected_batt,
          "timestamp": current_time,
          "voltage": new_voltage,
          "percentage": calc_percentage,
      }).execute()

      st.success(f"АКБ №{selected_batt} сохранен: {new_voltage}V")
      st.rerun()

  st.divider()
  with st.expander("ℹ️ Пороги AGM"):
    st.markdown("""
        * **12.5V+**: 🟢 Норма
        * **12.3V–12.4V**: 🟠 Скоро
        * **12.0V–12.2V**: 🔴 Пора
        * **< 12.0V**: ⚫ Пиздец
        """)

# --- ОСНОВНАЯ ЧАСТЬ: ОБЗОР ВСЕХ АККУМУЛЯТОРОВ ---

# Получение последних замеров по всем АКБ
history_res = (
    supabase.table("history").select("*").order("id", desc=True).execute()
)
history_data = history_res.data
history_df = pd.DataFrame(history_data)

cols = st.columns(4)

for index, row in batteries_df.iterrows():
  batt_id = int(row["id"])
  capacity = row["capacity"]

  # Фильтруем последний замер для данного АКБ
  batt_history = (
      history_df[history_df["battery_id"] == batt_id]
      if not history_df.empty
      else pd.DataFrame()
  )

  with cols[index]:
    st.subheader(f"🔋 АКБ №{batt_id} ({capacity:.0f} Ah)")

    if not batt_history.empty:
      last_row = batt_history.iloc[0]
      voltage = float(last_row["voltage"])
      pct = float(last_row["percentage"])
      ts = str(last_row["timestamp"]).replace("T", " ")[:19]

      status_text, color = get_status_color(voltage)

      if color == "green":
        border_css = "border-left: 5px solid #28a745; background-color: #f4fff4;"
      elif color == "orange":
        border_css = "border-left: 5px solid #fd7e14; background-color: #fff9f0;"
      elif color == "red":
        border_css = "border-left: 5px solid #dc3545; background-color: #fff0f0;"
      else:
        border_css = (
            "border-left: 5px solid #000000; background-color: #222222;"
            " color: #ffffff;"
        )

      text_color = "#ffffff" if color == "black" else "#000000"

      st.markdown(
          f"""
            <div style="padding: 10px; border-radius: 8px; {border_css} margin-bottom: 10px;">
                <h2 style="margin:0; color: {text_color};">{voltage:.2f} V</h2>
                <h4 style="margin:0; color: {text_color};">{pct:.1f}% заряда</h4>
                <p style="margin:5px 0 0 0; font-weight: bold; color: {text_color};">{status_text}</p>
                <p style="margin:5px 0 0 0; font-size: 11px; opacity: 0.8; color: {text_color};">🕒 {ts}</p>
            </div>
            """,
          unsafe_allow_html=True,
      )
    else:
      st.info("Замеров пока нет")

st.divider()

# --- ИСТОРИЯ ЗАМЕРОВ С ВОЗМОЖНОСТЬЮ УДАЛЕНИЯ ---
st.subheader("📊 История всех замеров")

if not history_df.empty:
  display_df = history_df.copy()

  # Приводим названия аккумуляторов
  display_df["battery_name"] = display_df["battery_id"].apply(
      lambda bid: (
          f"АКБ №{bid} ({batteries_df[batteries_df['id'] == bid]['capacity'].values[0]:.0f} Ah)"
          if not batteries_df[batteries_df["id"] == bid].empty
          else f"АКБ №{bid}"
      )
  )

  display_df[""] = False
  cols_order = ["", "timestamp", "battery_name", "voltage", "percentage"]
  display_df = display_df[cols_order]

  edited_df = st.data_editor(
      display_df,
      column_config={
          "": st.column_config.CheckboxColumn(
              "", help="Выбрать для удаления", default=False, width="small"
          ),
          "timestamp": st.column_config.TextColumn(
              "Дата и время", disabled=True
          ),
          "battery_name": st.column_config.TextColumn(
              "Аккумулятор", disabled=True
          ),
          "voltage": st.column_config.NumberColumn(
              "Вольтаж (V)", disabled=True, format="%.2f V"
          ),
          "percentage": st.column_config.NumberColumn(
              "Заряд (%)", disabled=True, format="%.1f%%"
          ),
      },
      hide_index=True,
      use_container_width=True,
      key="history_editor",
  )

  selected_rows = edited_df[edited_df[""] == True]

  if not selected_rows.empty:
    selected_indices = selected_rows.index
    selected_ids = history_df.loc[selected_indices, "id"].tolist()

    if st.button(
        f"🗑️ Подтвердить удаление выбранных записей ({len(selected_ids)} шт.)",
        type="primary",
    ):
      for target_id in selected_ids:
        supabase.table("history").delete().eq("id", target_id).execute()

      st.toast("❌ Запись(и) успешно удалены!", icon="🗑️")
      st.rerun()
else:
  st.info("История замеров пуста.")
