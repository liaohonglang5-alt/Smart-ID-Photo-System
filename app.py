from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont
import os
import cv2
import numpy as np
import io
import gc
from werkzeug.utils import secure_filename
import logging

# 只使用 rembg，不加载 MODNet 以节省内存
from rembg import remove

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['MODEL_FOLDER'] = 'pretrained/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 限制
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/background', methods=['GET', 'POST'])
def background():
    original_img = None
    removed_bg_img = None
    final_img = None

    if request.method == 'POST':
        file = request.files.get('file')
        bg_color = request.form.get('bg_color', '#ffffff')

        if file and allowed_file(file.filename):
            try:
                # 1. 保存原图
                filename = secure_filename(file.filename)
                original_path = os.path.join(app.config['UPLOAD_FOLDER'], f'original_{filename}')
                file.save(original_path)

                # 2. 使用 rembg 移除背景
                with open(original_path, 'rb') as f:
                    input_bytes = f.read()

                output_bytes = remove(input_bytes)
                removed_img = Image.open(io.BytesIO(output_bytes)).convert('RGBA')

                # 保存去背景图片（用于显示）
                removed_path = os.path.join(app.config['UPLOAD_FOLDER'], f'removed_{filename}')
                preview_bg = Image.new("RGB", removed_img.size, (255, 255, 255))
                preview_bg.paste(removed_img, mask=removed_img.split()[3])
                preview_bg.save(removed_path, 'JPEG')

                # 3. 应用新背景色
                if bg_color.startswith('#'):
                    bg_color = bg_color[1:]
                bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))

                final_bg = Image.new('RGBA', removed_img.size, bg_rgb + (255,))
                final_bg.paste(removed_img, mask=removed_img.split()[3])

                # 保存最终图
                final_path = os.path.join(app.config['UPLOAD_FOLDER'], f'final_{filename}')
                final_bg.convert('RGB').save(final_path, 'JPEG')

                # 设置图片路径供前端展示
                original_img = '/' + original_path
                removed_bg_img = '/' + removed_path
                final_img = '/' + final_path

                # 释放内存
                del removed_img, final_bg, preview_bg
                gc.collect()

            except Exception as e:
                print(f"处理过程中出错: {e}")
                return render_template('background.html', error=f"处理失败: {str(e)}")

    return render_template(
        'background.html',
        original_img=original_img,
        removed_bg_img=removed_bg_img,
        final_img=final_img
    )

@app.route('/crop', methods=['GET', 'POST'])
def crop():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = "crop_" + file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            output = crop_image(filepath)
            return send_file(output, mimetype='image/png', as_attachment=True, download_name='cropped.png')
    return render_template('crop.html')

@app.route('/watermark', methods=['GET', 'POST'])
def watermark():
    if request.method == 'POST':
        file = request.files['file']
        watermark_text = request.form.get('watermark', '')
        if file and allowed_file(file.filename):
            filename = "watermark_" + file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            output = add_watermark(filepath, watermark_text)
            return send_file(output, mimetype='image/png', as_attachment=True, download_name='watermarked.png')
    return render_template('watermark.html')

@app.route('/api/model_status')
def model_status():
    """API接口：返回模型状态"""
    status = {
        'modnet_available': False,
        'modnet_loaded': False,
        'fallback': 'rembg'
    }
    return jsonify(status)

@app.route('/portrait_cutout', methods=['GET', 'POST'])
def portrait_cutout():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # 使用 rembg 去除背景
            try:
                with open(filepath, 'rb') as f:
                    input_bytes = f.read()

                output_bytes = remove(input_bytes)
                result_img = Image.open(io.BytesIO(output_bytes)).convert('RGBA')

                # 保存结果图
                result_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cutout_' + filename)
                base, ext = os.path.splitext(result_path)
                result_path = base + '.png'
                result_img.save(result_path, 'PNG')

                # 释放内存
                del result_img
                gc.collect()

                return render_template('portrait_cutout.html',
                                       original_img='/' + filepath.replace('\\', '/'),
                                       cutout_img='/' + result_path.replace('\\', '/'))
            except Exception as e:
                print(f"背景去除失败: {e}")
                return render_template('portrait_cutout.html', error='背景去除失败')

    return render_template('portrait_cutout.html')

def crop_image(filepath):
    """裁剪图像"""
    img = Image.open(filepath)
    width, height = img.size
    left = width * 0.1
    top = height * 0.1
    right = width * 0.9
    bottom = height * 0.9
    cropped_img = img.crop((left, top, right, bottom))
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cropped.png')
    cropped_img.save(output_path)
    return output_path

def add_watermark(filepath, watermark):
    """添加水印"""
    img = Image.open(filepath).convert("RGBA")
    txt = Image.new('RGBA', img.size, (255,255,255,0))
    draw = ImageDraw.Draw(txt)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), watermark, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    x = img.width - text_width - 10
    y = img.height - text_height - 10
    draw.text((x, y), watermark, fill=(255, 255, 255, 128), font=font)
    combined = Image.alpha_composite(img, txt)
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'watermarked.png')
    combined.convert('RGB').save(output_path)
    return output_path

if __name__ == '__main__':
    # 创建必要的目录
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['MODEL_FOLDER'], exist_ok=True)

    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)