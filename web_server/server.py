from flask import Flask, render_template, jsonify, request
import os

app = Flask(__name__,
            static_folder='../frontend/static',
            template_folder='../frontend')

# Тестовые товары
TEST_PRODUCTS = [
    {"id": 1, "name": "Elf Bar BC5000", "price": 1299, "category": "Одноразки", "stock": 10, "image_url": "https://via.placeholder.com/300x300/667eea/ffffff?text=Elf+Bar"},
    {"id": 2, "name": "HQD Cuvie Plus", "price": 1199, "category": "Одноразки", "stock": 15, "image_url": "https://via.placeholder.com/300x300/764ba2/ffffff?text=HQD"},
    {"id": 3, "name": "Puff Bar Plus", "price": 899, "category": "Одноразки", "stock": 20, "image_url": "https://via.placeholder.com/300x300/48bb78/ffffff?text=Puff+Bar"},
    {"id": 4, "name": "Жидкость HQD 30мл", "price": 499, "category": "Жидкости", "stock": 30, "image_url": "https://via.placeholder.com/300x300/ed8936/ffffff?text=Жидкость+HQD"},
    {"id": 5, "name": "Жидкость Elf 30мл", "price": 549, "category": "Жидкости", "stock": 25, "image_url": "https://via.placeholder.com/300x300/ed64a6/ffffff?text=Жидкость+Elf"},
    {"id": 6, "name": "Зарядка Type-C", "price": 299, "category": "Аксессуары", "stock": 50, "image_url": "https://via.placeholder.com/300x300/4299e1/ffffff?text=Зарядка"}
]

TEST_CATEGORIES = [
    {"id": 1, "name": "Одноразки"},
    {"id": 2, "name": "Жидкости"},
    {"id": 3, "name": "Картриджи"},
    {"id": 4, "name": "Аксессуары"}
]


@app.route('/')
def home():
    """Главная страница Mini App"""
    return render_template('index.html')


@app.route('/api/products')
def get_products():
    """API: Получить товары"""
    category = request.args.get('category', 'all')

    if category == 'all' or not category:
        return jsonify(TEST_PRODUCTS)
    else:
        filtered = [p for p in TEST_PRODUCTS if p['category'] == category]
        return jsonify(filtered)


@app.route('/api/categories')
def get_categories():
    """API: Получить категории"""
    return jsonify(TEST_CATEGORIES)


if __name__ == '__main__':
    print('🚀 Сервер Mini App запущен!')
    print('📂 Открой: http://localhost:5000')
    print('📦 API товаров: http://localhost:5000/api/products')
    app.run(host='0.0.0.0', port=5000, debug=True)