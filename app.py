from flask import Flask, request, jsonify, g
from flask_cors import CORS
import sqlite3
import hashlib
import time

# 初始化Flask应用
app = Flask(__name__)
CORS(app, supports_credentials=True)  # 修复跨域问题，支持凭证

# 数据库配置
DATABASE = 'cangjingge.db'

# 连接数据库
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # 支持字典形式获取数据
    return db

# 关闭数据库连接
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# 初始化数据库表（用户表+内容表+求书表+收藏表）
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # 1. 用户表：id/账号/密码/昵称/创建时间
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                nickname TEXT NOT NULL,
                create_time TEXT NOT NULL
            )
        ''')
        # 2. 内容表（教材/笔记）：id/用户id/类型/标题/详情/价格/方式/发布时间/是否推荐
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                info TEXT NOT NULL,
                price REAL NOT NULL,
                way TEXT NOT NULL,
                create_time TEXT NOT NULL,
                is_hot INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES user (id)
            )
        ''')
        # 3. 求书表：id/用户id/类型/标题/详情/发布时间
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS want (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                info TEXT NOT NULL,
                create_time TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user (id)
            )
        ''')
        # 4. 收藏表：id/用户id/内容id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collect (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (content_id) REFERENCES content (id),
                UNIQUE (user_id, content_id)  # 唯一约束，避免重复收藏
            )
        ''')
        db.commit()
        print("数据库表初始化成功！")

# 密码加密（MD5，简单安全，避免明文存储）
def md5_encrypt(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()

# ---------------------- 用户接口：注册/登录 ----------------------
# 注册接口：POST /api/register  参数：username/password/nickname
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'msg': '请提交JSON格式数据'})
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        nickname = data.get('nickname', '藏经阁用户').strip()
        
        if not username or not password:
            return jsonify({'code': -1, 'msg': '账号和密码不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        # 检查账号是否已存在
        cursor.execute('SELECT * FROM user WHERE username = ?', (username,))
        if cursor.fetchone():
            return jsonify({'code': -1, 'msg': '账号已存在'})
        # 插入用户数据，密码加密
        create_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        cursor.execute('''
            INSERT INTO user (username, password, nickname, create_time)
            VALUES (?, ?, ?, ?)
        ''', (username, md5_encrypt(password), nickname, create_time))
        db.commit()
        return jsonify({'code': 0, 'msg': '注册成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'注册失败：{str(e)}'})

# 登录接口：POST /api/login  参数：username/password
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'msg': '请提交JSON格式数据'})
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'code': -1, 'msg': '账号和密码不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM user WHERE username = ? AND password = ?', 
                      (username, md5_encrypt(password)))
        user = cursor.fetchone()
        if not user:
            return jsonify({'code': -1, 'msg': '账号或密码错误'})
        # 返回用户信息（id/账号/昵称），用于前端鉴权
        return jsonify({
            'code': 0, 'msg': '登录成功',
            'data': {
                'user_id': user['id'],
                'username': user['username'],
                'nickname': user['nickname']
            }
        })
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'登录失败：{str(e)}'})

# ---------------------- 内容接口：发布/查询/收藏/我想要 ----------------------
# 发布内容（教材/笔记）：POST /api/publish_content  参数：user_id/type/title/info/price/way
@app.route('/api/publish_content', methods=['POST'])
def publish_content():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'msg': '请提交JSON格式数据'})
        
        required = ['user_id', 'type', 'title', 'info', 'price', 'way']
        if not all(k in data for k in required):
            return jsonify({'code': -1, 'msg': '参数不完整'})
        
        # 数据清洗
        user_id = data['user_id']
        type_ = data['type'].strip()
        title = data['title'].strip()
        info = data['info'].strip()
        price = float(data['price'])
        way = data['way'].strip()
        
        if not title or not info:
            return jsonify({'code': -1, 'msg': '标题和详情不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        create_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        # 免费笔记设为学霸推荐（is_hot=1）
        is_hot = 1 if (type_ == 'note' and price == 0) else 0
        cursor.execute('''
            INSERT INTO content (user_id, type, title, info, price, way, create_time, is_hot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, type_, title, info, price, way, create_time, is_hot))
        db.commit()
        return jsonify({'code': 0, 'msg': '发布成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'发布失败：{str(e)}'})

# 查询内容（按类型/关键词/价格）：GET /api/get_content  参数：user_id/type/keyword/price
@app.route('/api/get_content', methods=['GET'])
def get_content():
    try:
        user_id = request.args.get('user_id', '')
        type_ = request.args.get('type', 'all')
        keyword = request.args.get('keyword', '')
        price = request.args.get('price', 'all')
        
        if not user_id:
            return jsonify({'code': -1, 'msg': '用户ID不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        # 基础查询语句
        sql = 'SELECT c.*, u.nickname as publish_user FROM content c LEFT JOIN user u ON c.user_id = u.id WHERE 1=1'
        params = []
        # 类型筛选
        if type_ != 'all':
            sql += ' AND c.type = ?'
            params.append(type_)
        # 关键词筛选（标题/详情）
        if keyword:
            sql += ' AND (c.title LIKE ? OR c.info LIKE ?)'
            params.append(f'%{keyword}%')
            params.append(f'%{keyword}%')
        # 价格筛选
        if price == 'free':
            sql += ' AND c.price = 0'
        elif price == 'low':
            sql += ' AND c.price > 0 AND c.price <= 50'
        elif price == 'high':
            sql += ' AND c.price > 50'
        # 按发布时间倒序
        sql += ' ORDER BY c.create_time DESC'
        
        cursor.execute(sql, params)
        content_list = [dict(row) for row in cursor.fetchall()]
        # 补充收藏状态：当前用户是否收藏了该内容
        for content in content_list:
            cursor.execute('SELECT * FROM collect WHERE user_id = ? AND content_id = ?', (user_id, content['id']))
            content['is_collect'] = 1 if cursor.fetchone() else 0
            # 处理价格文字/方式文字
            content['price_text'] = '免费' if content['price'] == 0 else f'¥{content["price"]}'
            content['way_text'] = '校内自提' if content['way'] == 'self' else '快递到付' if content['way'] == 'express' else '线上发送'
            content['type_text'] = '二手教材' if content['type'] == 'book' else '学霸笔记'
        
        return jsonify({'code': 0, 'data': content_list})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'查询失败：{str(e)}', 'data': []})

# 收藏/取消收藏：POST /api/collect  参数：user_id/content_id
@app.route('/api/collect', methods=['POST'])
def collect():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'msg': '请提交JSON格式数据'})
        
        user_id = data.get('user_id', '')
        content_id = data.get('content_id', '')
        
        if not user_id or not content_id:
            return jsonify({'code': -1, 'msg': '参数不完整'})
        
        db = get_db()
        cursor = db.cursor()
        # 检查是否已收藏
        cursor.execute('SELECT * FROM collect WHERE user_id = ? AND content_id = ?', (user_id, content_id))
        if cursor.fetchone():
            # 取消收藏
            cursor.execute('DELETE FROM collect WHERE user_id = ? AND content_id = ?', (user_id, content_id))
            db.commit()
            return jsonify({'code': 0, 'msg': '取消收藏成功'})
        else:
            # 收藏
            cursor.execute('INSERT INTO collect (user_id, content_id) VALUES (?, ?)', (user_id, content_id))
            db.commit()
            return jsonify({'code': 0, 'msg': '收藏成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'操作失败：{str(e)}'})

# ---------------------- 求书接口：发布/查询 ----------------------
# 发布求书需求：POST /api/publish_want  参数：user_id/type/title/info
@app.route('/api/publish_want', methods=['POST'])
def publish_want():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'msg': '请提交JSON格式数据'})
        
        required = ['user_id', 'type', 'title', 'info']
        if not all(k in data for k in required):
            return jsonify({'code': -1, 'msg': '参数不完整'})
        
        user_id = data['user_id']
        type_ = data['type'].strip()
        title = data['title'].strip()
        info = data['info'].strip()
        
        if not title or not info:
            return jsonify({'code': -1, 'msg': '标题和详情不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        create_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        cursor.execute('''
            INSERT INTO want (user_id, type, title, info, create_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, type_, title, info, create_time))
        db.commit()
        return jsonify({'code': 0, 'msg': '需求发布成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'发布失败：{str(e)}'})

# 查询求书需求：GET /api/get_want
@app.route('/api/get_want', methods=['GET'])
def get_want():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT w.*, u.nickname as want_user FROM want w LEFT JOIN user u ON w.user_id = u.id ORDER BY w.create_time DESC')
        want_list = [dict(row) for row in cursor.fetchall()]
        # 处理类型文字
        for want in want_list:
            want['type_text'] = '求教材' if want['type'] == 'book' else '求笔记'
        return jsonify({'code': 0, 'data': want_list})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'查询失败：{str(e)}', 'data': []})

# ---------------------- 个人中心接口：我的发布/我的收藏 ----------------------
# 我的发布：GET /api/my_publish  参数：user_id
@app.route('/api/my_publish', methods=['GET'])
def my_publish():
    try:
        user_id = request.args.get('user_id', '')
        if not user_id:
            return jsonify({'code': -1, 'msg': '用户ID不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM content WHERE user_id = ? ORDER BY create_time DESC', (user_id,))
        publish_list = [dict(row) for row in cursor.fetchall()]
        # 补充格式信息
        for p in publish_list:
            p['price_text'] = '免费' if p['price'] == 0 else f'¥{p["price"]}'
            p['way_text'] = '校内自提' if p['way'] == 'self' else '快递到付' if p['way'] == 'express' else '线上发送'
            p['type_text'] = '二手教材' if p['type'] == 'book' else '学霸笔记'
            p['is_collect'] = 0  # 自己发布的默认未收藏
        return jsonify({'code': 0, 'data': publish_list})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'查询失败：{str(e)}', 'data': []})

# 我的收藏：GET /api/my_collect  参数：user_id
@app.route('/api/my_collect', methods=['GET'])
def my_collect():
    try:
        user_id = request.args.get('user_id', '')
        if not user_id:
            return jsonify({'code': -1, 'msg': '用户ID不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT c.*, u.nickname as publish_user FROM content c
            LEFT JOIN collect cl ON c.id = cl.content_id
            LEFT JOIN user u ON c.user_id = u.id
            WHERE cl.user_id = ?
            ORDER BY c.create_time DESC
        ''', (user_id,))
        collect_list = [dict(row) for row in cursor.fetchall()]
        # 补充格式信息
        for c in collect_list:
            c['price_text'] = '免费' if c['price'] == 0 else f'¥{c["price"]}'
            c['way_text'] = '校内自提' if c['way'] == 'self' else '快递到付' if c['way'] == 'express' else '线上发送'
            c['type_text'] = '二手教材' if c['type'] == 'book' else '学霸笔记'
            c['is_collect'] = 1
        return jsonify({'code': 0, 'data': collect_list})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'查询失败：{str(e)}', 'data': []})

# 初始化数据库
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)  # host=0.0.0.0 允许公网访问