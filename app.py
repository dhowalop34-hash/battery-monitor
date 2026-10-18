from datetime import datetime
import sqlite3
import pandas as pd
import streamlit as st

DB_NAME = "batteries.db"


def init_db():
  """Инициализация базы данных и первичное заполнение аккумуляторов"""
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS batteries (
            id INTEGER PRIMARY KEY,
            capacity REAL,
            type TEXT
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id INTEGER,
            timestamp TEXT,
            voltage REAL,
            percentage REAL,
            FOREIGN KEY (battery_id) REFERENCES batteries (id)
        )
    """)

  cursor.execute("SELECT COUNT(*) FROM batteries")
  if cursor.fetchone()[0] == 0:
    initial_batteries = [
        (1, 26.0, "AGM 12V"),
        (2, 5.0, "AGM 12V"),
        (3, 5.0, "AGM 12V"),
        (4, 5.0, "AGM 12V"),
    ]
    cursor.executemany(
        "INSERT INTO batteries (id, capacity, type) VALUES (?, ?, ?)",
        initial_batteries,
    )
    conn.commit()

  conn.close()


def agm_voltage_to_percentage(v):
  """Точный расчет процента заряда для 12V AGM (12.0V ≈ 30%)"""
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
  """Возвращает плашку/иконку статуса по вольтажу"""
  if voltage >= 12.5:
    return "🟢 Норма", "green"
  elif voltage >= 12.3:
    return "🟠 Скоро заряжать", "orange"
  elif voltage >= 12.0:
    return "🔴 12V — Пора заряжать!", "red"
  else:
    return "⚫ Ниже 12V — Пиздец!", "black"


# Настройка ширины страницы
st.set_page_config(
    page_title="Мониторинг АКБ",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.title("🔋 Мониторинг всех аккумуляторов")

# --- БОКОВАЯ ПАНЕЛЬ (Sidebar) ДЛЯ ВВОДА ЗАМЕРА ---
with st.sidebar:
  st.header("📝 Новый замер")

  conn = sqlite3.connect(DB_NAME)
  batteries_df = pd.read_sql("SELECT * FROM batteries", conn)
  conn.close()

  battery_ids = batteries_df["id"].tolist()

  with st.form(key="voltage_form"):
    selected_batt = st.selectbox(
        "Выберите АКБ:",
        battery_ids,
        format_func=lambda x: (
            f"АКБ №{x} ({batteries_df[batteries_df['id'] == x]['capacity'].values[0]} Ah)"
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

      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      cursor.execute(
          """
                INSERT INTO history (battery_id, timestamp, voltage, percentage)
                VALUES (?, ?, ?, ?)
            """,
          (selected_batt, current_time, new_voltage, calc_percentage),
      )
      conn.commit()
      conn.close()

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

conn = sqlite3.connect(DB_NAME)
query_last = """
    SELECT b.id, b.capacity, h.voltage, h.percentage, h.timestamp
    FROM batteries b
    LEFT JOIN history h ON h.id = (
        SELECT max(id) FROM history WHERE battery_id = b.id
    )
    ORDER BY b.id ASC
"""
last_records_df = pd.read_sql(query_last, conn)
conn.close()

cols = st.columns(4)

for index, row in last_records_df.iterrows():
  batt_id = int(row["id"])
  capacity = row["capacity"]
  voltage = row["voltage"]
  pct = row["percentage"]
  ts = row["timestamp"]

  with cols[index]:
    st.subheader(f"🔋 АКБ №{batt_id} ({capacity:.0f} Ah)")

    if pd.notnull(voltage):
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

# --- ИСТОРИЯ ЗАМЕРОВ С КОМПАКТНЫМ СТОЛБЦОМ УДАЛЕНИЯ ---
st.subheader("📊 История всех замеров")

conn = sqlite3.connect(DB_NAME)
all_history_df = pd.read_sql(
    """
    SELECT h.id, h.timestamp, h.battery_id, b.capacity, h.voltage, h.percentage
    FROM history h
    JOIN batteries b ON h.battery_id = b.id
    ORDER BY h.id DESC
""",
    conn,
)
conn.close()

if not all_history_df.empty:
  display_df = all_history_df.copy()
  display_df["battery_name"] = display_df.apply(
      lambda r: f"АКБ №{int(r['battery_id'])} ({r['capacity']:.0f} Ah)", axis=1
  )

  display_df["❌"] = False

  cols_order = ["❌", "timestamp", "battery_name", "voltage", "percentage"]
  display_df = display_df[cols_order]

  # Точный CSS-стиль для сжатия первой колонки таблицы
  st.markdown(
      """
        <style>
        div[data-testid="stDataFrame"] div[data-baseweb="table"] th:nth-child(1),
        div[data-testid="stDataFrame"] div[data-baseweb="table"] td:nth-child(1) {
            width: 55px !important;
            min-width: 55px !important;
            max-width: 55px !important;
            text-align: center !important;
        }
        </style>
    """,
      unsafe_allow_html=True,
  )

  edited_df = st.data_editor(
      display_df,
      column_config={
          "❌": st.column_config.CheckboxColumn(
              "❌УДАЛЕНИЯ",
              help="Поставьте галочку для удаления",
              default=False,
              width="small",
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

  selected_rows = edited_df[edited_df["❌"] == True]

  if not selected_rows.empty:
    selected_indices = selected_rows.index
    selected_ids = all_history_df.loc[selected_indices, "id"].tolist()

    if st.button(
        f"🗑️ Подтвердить удаление выбранных записей ({len(selected_ids)} шт.)",
        type="primary",
    ):
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      for target_id in selected_ids:
        cursor.execute("DELETE FROM history WHERE id = ?", (target_id,))
      conn.commit()
      conn.close()

      st.toast("❌ Запись(и) успешно удалены!", icon="🗑️")
      st.rerun()

else:
  st.info("История замеров пуста.")