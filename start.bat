@echo off
chcp 65001 > nul
echo Запуск сайта для аккумуляторов...
python -m streamlit run app.py
pause