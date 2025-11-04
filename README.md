# Gradient-Backend

### Для початку потрібно створити серидовище в яке будуть завантажуватись усі необхідні тули:
    python -m venv .venv

### Щоб перейти в серидовище потрібно вписати:
    .venv\Scripts\activate
    
### І для інтеграції fastapi, в серидовищі .venv вписуємо:
    pip install fastapi uvicorn

### Для запуску backend потрібна команда:
    uvicorn main:app --reload
    
### Комбінація клавіш для зупинки процесу (backend):
    Ctrl + C

### Для встановлення залежностей потрібно вписати:
    pip install -r requirements.txt

### А для того щоб створити залежності потрібно:
    pip freeze > requirements.txt

### <span style="color:red">Це речення червоного кольору</span>
