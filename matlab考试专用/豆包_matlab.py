from flask import Flask, request, render_template, jsonify, send_from_directory
import os
import time
import json
import base64
from PIL import Image
import io
import datetime
import uuid
import threading
from volcenginesdkarkruntime import Ark
from pyngrok import ngrok
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'math_images'
app.config['RESULTS_FOLDER'] = 'math_solutions'

# 确保上传和结果文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# 初始化客户端
client = Ark(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # 从环境变量中获取您的 API Key
    api_key="你自己的key"
)

# 保存任务状态的字典
tasks = {}


# 编码图片函数
def encode_image(image_path):
    """
    将图片转换为base64编码
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_example_markdown():
    """
    返回一个示例Markdown文档，用于指导AI生成正确格式的输出
    """
    example_folder = "example_solutions"
    # 确保示例文件夹存在
    os.makedirs(example_folder, exist_ok=True)

    # 尝试读取示例文件，如果不存在则返回None
    example_files = [f for f in os.listdir(example_folder) if f.endswith('.md')]
    if not example_files:
        return None

    # 随机选择一个示例文件
    example_file = os.path.join(example_folder, example_files[0])
    with open(example_file, 'r', encoding='utf-8') as f:
        return f.read()


# MATLAB专用的提示模板函数
def create_matlab_prompt(question_text, question_type=None):
    """
    生成针对MATLAB考试题目的专业提示词

    参数:
    question_text: 用户输入的题目文本或问题描述
    question_type: MATLAB问题类型 (basic, plot, diff_eq, matrix, symbolic, statistics, 或 None为自动)

    返回:
    格式化的提示词
    """
    # 基础系统提示词
    system_prompt = (
        "你是一位MATLAB专家和工程数学教师，熟练掌握MATLAB各种应用场景，特别擅长解决考试类问题。"
        "请分析下面的MATLAB问题，并提供详细的解决方案，包括完整的代码、步骤解释和结果分析。"
        "你的回答应当包括以下几个部分:\n"
        "1. 题目分析: 简要分析问题要求和解题思路\n"
        "2. 完整代码: 提供可以直接运行的MATLAB代码\n"
        "3. 代码解释: 逐行或逐段解释代码的功能和原理\n"
        "4. 预期输出: 说明代码运行后预期的结果\n"
        "5. 优化建议: 如有可能，提供代码优化或简化的方法\n\n"
        "请确保代码遵循MATLAB的语法规范，变量命名清晰，并添加足够的注释。"
    )

    # 根据问题类型添加专业提示
    type_specific_prompts = {
        "basic": (
            "这是一个MATLAB基础操作题目。请特别注意:\n"
            "- 变量类型和赋值方式\n"
            "- 数组索引规则（MATLAB从1开始索引）\n"
            "- 使用冒号操作符创建向量和进行切片\n"
            "- 矩阵运算中.*、./等点运算符的使用\n"
            "- 合理使用内置函数如size(), length(), numel()等"
        ),

        "plot": (
            "这是一个MATLAB绘图题目。请特别注意:\n"
            "- 使用正确的绘图函数(plot, scatter, bar, histogram, surf, contour等)\n"
            "- 设置合适的轴标签(xlabel, ylabel, zlabel)和标题(title)\n"
            "- 添加图例(legend)和网格线(grid)\n"
            "- 正确设置轴的范围和刻度(xlim, ylim, axis等)\n"
            "- 使用figure和subplot管理多个图形\n"
            "- 如需要，使用hold on/hold off添加多条曲线\n"
            "- 考虑使用适当的颜色和线型，提高图形可读性"
        ),

        "diff_eq": (
            "这是一个MATLAB微分方程题目。请特别注意:\n"
            "- 将高阶微分方程转化为一阶方程组\n"
            "- 正确定义微分方程函数句柄\n"
            "- 选择适当的求解器(ode45, ode23, ode15s等)\n"
            "- 设置合适的时间跨度和初始条件\n"
            "- 处理结果时正确访问求解器返回的结构体\n"
            "- 考虑使用dsolve处理符号解\n"
            "- 绘制解的图形并添加适当的标签"
        ),

        "matrix": (
            "这是一个MATLAB矩阵操作题目。请特别注意:\n"
            "- 矩阵的创建、转置、求逆等基本操作\n"
            "- 矩阵的四则运算(区分.*和*等)\n"
            "- 特征值和特征向量计算(eig函数)\n"
            "- 矩阵分解技术(LU, QR, Cholesky等)\n"
            "- 线性方程组求解(直接法或迭代法)\n"
            "- 稀疏矩阵的处理方法\n"
            "- 矩阵条件数和范数的计算"
        ),

        "symbolic": (
            "这是一个MATLAB符号计算题目。请特别注意:\n"
            "- 使用syms正确定义符号变量\n"
            "- 符号函数的定义和操作\n"
            "- 符号微分(diff)和积分(int)运算\n"
            "- 符号方程求解(solve)\n"
            "- 极限计算(limit)\n"
            "- 级数展开(taylor)\n"
            "- 符号表达式简化(simplify, collect, expand等)\n"
            "- 符号结果的数值计算(subs, vpa)"
        ),

        "statistics": (
            "这是一个MATLAB统计分析题目。请特别注意:\n"
            "- 描述性统计量的计算(mean, median, std, var等)\n"
            "- 概率分布函数的使用(pdf, cdf, random等)\n"
            "- 随机数生成(rand, randn, randi)\n"
            "- 假设检验的实现和解释\n"
            "- 回归分析(polyfit, regress等)\n"
            "- 统计图表的绘制(histogram, boxplot等)\n"
            "- 统计工具箱函数的正确调用"
        )
    }

    # 自动检测问题类型的提示
    auto_detect_prompt = (
        "请根据问题内容，识别这是哪类MATLAB问题(基础操作、绘图、微分方程、矩阵运算、符号计算或统计分析)，"
        "并按照相应类型的最佳实践来提供解答。"
    )

    # 拼接最终提示词
    final_prompt = system_prompt

    if question_type and question_type in type_specific_prompts:
        final_prompt += "\n\n" + type_specific_prompts[question_type]
    else:
        final_prompt += "\n\n" + auto_detect_prompt

    # 添加考试专用提示
    exam_specific_prompt = (
        "\n\n由于这是考试情境，请特别注意:\n"
        "- 代码的效率和简洁性\n"
        "- 提供多种可能的解题方法比较\n"
        "- 避免使用过于高级或不常见的函数\n"
        "- 点出常见错误和易混淆的概念\n"
        "- 强调MATLAB语法的特殊性（如区分'和\"，1-索引等）\n"
        "- 在关键步骤添加注释，便于理解和复习\n"
        "- 使用常规解法，避免复杂技巧，除非明确要求"
    )

    final_prompt += exam_specific_prompt

    # 添加用户问题
    user_question = f"\n\n问题: {question_text}"
    final_prompt += user_question

    return final_prompt


# MATLAB问题类型映射
MATLAB_PROBLEM_TYPES = {
    "basic": "MATLAB基础操作",
    "plot": "MATLAB绘图",
    "diff_eq": "微分方程",
    "matrix": "矩阵运算",
    "symbolic": "符号计算",
    "statistics": "统计分析"
}


# 调用豆包API的MATLAB专用函数
def ask_matlab_question(question_text, problem_type=None, model="doubao-1-5-vision-pro-32k-250115", max_retries=3, **kwargs):
    """
    提交MATLAB问题并获取解答

    参数:
    question_text: 用户输入的MATLAB问题
    problem_type: MATLAB问题类型
    model: 使用的模型
    max_retries: 最大重试次数
    **kwargs: 其他参数

    返回:
    带有解答的字典
    """
    # 生成专用提示词
    prompt = create_matlab_prompt(question_text, problem_type)

    # 准备系统消息内容
    system_content = (
        "你是一位MATLAB编程专家，特别擅长帮助学生解决MATLAB考试中的问题。"
        "请使用Markdown格式输出，提供详尽的代码解析和详细的解题思路。"
        "代码必须使用```matlab 和 ``` 格式化，确保可以直接复制运行。"
    )

    # 构建系统消息和用户消息
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]

    # 设置默认参数，可被kwargs覆盖
    params = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,  # 降低温度以提高精确性
        "max_tokens": 4000,  # 增加token以容纳完整代码和解释
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0
    }

    # 使用传入的kwargs更新默认参数
    params.update(kwargs)

    # 添加重试机制
    for attempt in range(max_retries):
        try:
            print(f"🔍 正在解答MATLAB问题 (尝试 {attempt + 1}/{max_retries})...")

            # 使用与ask_with_math_image相同的client对象
            response = client.chat.completions.create(**params)

            answer = response.choices[0].message.content

            # 解析答案的各个部分
            parts = {
                "full_response": answer
            }

            # 尝试提取各个部分
            if "## 题目分析" in answer:
                parts["problem_analysis"] = extract_section(answer, "## 题目分析",
                                                            find_next_section_md(answer, "## 题目分析"))

            if "## 完整代码" in answer:
                parts["complete_code"] = extract_section(answer, "## 完整代码",
                                                         find_next_section_md(answer, "## 完整代码"))

            if "## 代码解释" in answer:
                parts["code_explanation"] = extract_section(answer, "## 代码解释",
                                                            find_next_section_md(answer, "## 代码解释"))

            if "## 预期输出" in answer:
                parts["expected_output"] = extract_section(answer, "## 预期输出",
                                                           find_next_section_md(answer, "## 预期输出"))

            if "## 优化建议" in answer:
                parts["optimization"] = extract_section(answer, "## 优化建议",
                                                        find_next_section_md(answer, "## 优化建议"))

            return parts

        except Exception as e:
            print(f"❌ 错误: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                print(f"⏳ 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print("❌ 达到最大重试次数，放弃请求")
                raise e


# 添加到路由
@app.route('/matlab', methods=['POST'])
def process_matlab():
    try:
        # 获取请求数据
        data = request.json

        if not data or 'question' not in data:
            return jsonify({'error': '请提供MATLAB问题'}), 400

        question = data['question']
        problem_type = data.get('problem_type', None)

        # 创建唯一的任务ID
        task_id = str(uuid.uuid4())

        # 创建任务记录
        tasks[task_id] = {
            'id': task_id,
            'question': question,
            'problem_type': problem_type,
            'status': 'pending',
            'created_at': datetime.datetime.now().isoformat()
        }

        # 启动异步处理任务
        thread = threading.Thread(target=process_matlab_async, args=(task_id, question, problem_type))
        thread.daemon = True
        thread.start()

        return jsonify({
            'task_id': task_id,
            'status': 'pending',
            'message': 'MATLAB问题正在处理中...'
        })

    except Exception as e:
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500


# MATLAB问题的异步处理函数
def process_matlab_async(task_id, question, problem_type=None):
    try:
        # 更新任务状态为处理中
        tasks[task_id]['status'] = 'processing'

        # 处理MATLAB问题
        result = ask_matlab_question(question, problem_type)

        # 生成结果文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"matlab_{task_id}_{timestamp}.md"

        # 保存Markdown结果
        output_path = os.path.join(app.config['RESULTS_FOLDER'], output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["full_response"])

        # 更新任务状态为完成
        tasks[task_id].update({
            'status': 'completed',
            'result_file': output_filename,
            'result': result["full_response"]
        })

    except Exception as e:
        # 更新任务状态为失败
        tasks[task_id].update({
            'status': 'failed',
            'error': str(e)
        })
        print(f"MATLAB任务 {task_id} 失败: {e}")

# 辅助函数：找到下一个Markdown章节的标记
def find_next_section_md(text, current_marker):
    # 可能的Markdown章节标记
    section_markers = ["## 题目", "## 问题", "## 分析", "## 方法选择", "## 方法",
                       "## 推导过程", "## 计算过程", "## 结果", "## 答案", "## 验证", "## 检验"]

    # 从当前标记之后的文本中找起始位置
    start_pos = text.find(current_marker) + len(current_marker)
    min_pos = float('inf')
    next_marker = None

    # 找到当前标记之后最近的下一个标记
    for marker in section_markers:
        if marker == current_marker:
            continue
        pos = text.find(marker, start_pos)
        if pos != -1 and pos < min_pos:
            min_pos = pos
            next_marker = marker

    return next_marker


# 辅助函数：提取章节内容
def extract_section(text, start_marker, end_marker=None):
    if end_marker:
        section_text = text.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
    else:
        section_text = text.split(start_marker, 1)[1].strip()
    return section_text


# 数学领域的专门提示模板
MATH_IMAGE_TEMPLATES = {
    "calculus": "这是一道微积分问题。请特别关注积分技巧、极限计算和收敛性分析。使用Markdown格式输出，数学公式使用LaTeX格式。",
    "linear_algebra": "这是一道线性代数问题。请使用矩阵表示，并从线性变换的角度进行分析。必要时讨论特征值和特征向量。使用Markdown格式输出，数学公式使用LaTeX格式。",
    "probability": "这是一道概率论问题。请明确指出所用的概率分布，并详细说明随机变量的性质。必要时使用矩和母函数。使用Markdown格式输出，数学公式使用LaTeX格式。",
    "geometry": "这是一道几何问题。请使用解析几何或向量方法处理，并附上必要的图形解释。使用Markdown格式输出，数学公式使用LaTeX格式。",
    "differential_equations": "这是一道微分方程问题。请指明方程类型，选择适当的求解方法，并验证解的完整性和唯一性。使用Markdown格式输出，数学公式使用LaTeX格式。"
}


# 启动异步任务
def process_image_async(task_id, image_path, problem_type=None):
    try:
        # 更新任务状态为处理中
        tasks[task_id]['status'] = 'processing'

        # 使用对应类型的数学模板
        template = MATH_IMAGE_TEMPLATES.get(problem_type, None)

        # 添加额外的文字提示
        text_prompt = ("请识别并解答图片中的数学问题。"
                       "首先准确描述你在图片中看到的问题，然后按照分析、方法选择、推导过程、结果和验证五个步骤进行详细解答。"
                       "请使用Markdown格式输出，严格使用二级标题（##）分隔各个部分，数学公式使用LaTeX格式。")

        # 处理图片中的数学问题
        result = ask_with_math_image(
            image_path,
            text_prompt=text_prompt,
            custom_instruction=template,
            temperature=0.4
        )

        # 生成结果文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_filename = f"{base_name}_{timestamp}.md"

        # 保存Markdown结果 - 不进行任何LaTeX格式转换
        output_path = os.path.join(app.config['RESULTS_FOLDER'], output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["full_response"])

        # 更新任务状态为完成
        tasks[task_id].update({
            'status': 'completed',
            'result_file': output_filename,
            'result': result["full_response"]
        })

    except Exception as e:
        # 更新任务状态为失败
        tasks[task_id].update({
            'status': 'failed',
            'error': str(e)
        })
        print(f"任务 {task_id} 失败: {e}")


@app.route('/')
def index():
    return render_template('index1.html', math_types=list(MATH_IMAGE_TEMPLATES.keys()))


@app.route('/upload', methods=['POST'])
def upload_file():
    # 添加调试日志
    print("\n===== 收到上传请求 =====")
    print("请求方法:", request.method)
    print("表单数据:", request.form)
    print("文件:", request.files)

    # 检查是否有文件被上传
    if 'file' not in request.files:
        print("错误: 没有文件部分")
        return jsonify({'error': '没有选择文件'}), 400

    file = request.files['file']

    # 如果用户没有选择文件，浏览器也会发送一个空文件
    if file.filename == '':
        print("错误: 文件名为空")
        return jsonify({'error': '没有选择文件'}), 400

    # 获取问题类型
    problem_type = request.form.get('problem_type', None)
    print(f"问题类型: {problem_type}")

    # 创建唯一的任务ID
    task_id = str(uuid.uuid4())
    print(f"生成任务ID: {task_id}")

    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # 保存上传的文件
    filename = f"{task_id}_{file.filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    print(f"保存文件到: {file_path}")

    try:
        file.save(file_path)
        print(f"文件保存成功: {os.path.exists(file_path)}")
    except Exception as e:
        print(f"文件保存失败: {e}")
        return jsonify({'error': f'文件保存失败: {str(e)}'}), 500

    # 创建任务记录
    tasks[task_id] = {
        'id': task_id,
        'file_name': file.filename,
        'file_path': file_path,
        'problem_type': problem_type,
        'status': 'pending',
        'created_at': datetime.datetime.now().isoformat()
    }
    print(f"任务记录创建成功: {tasks[task_id]}")

    # 启动异步处理任务
    try:
        thread = threading.Thread(target=process_image_async, args=(task_id, file_path, problem_type))
        thread.daemon = True
        thread.start()
        print(f"异步任务启动成功")
    except Exception as e:
        print(f"异步任务启动失败: {e}")
        return jsonify({'error': f'任务启动失败: {str(e)}'}), 500

    response = {
        'task_id': task_id,
        'status': 'pending',
        'message': '文件已上传，开始处理...'
    }
    print(f"返回响应: {response}")
    return jsonify(response)


@app.route('/results/<path:filename>')
def download_file(filename):
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)


@app.route('/status/<task_id>')
def get_task_status(task_id):
    if task_id not in tasks:
        return jsonify({'error': '找不到任务'}), 404

    return jsonify(tasks[task_id])


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=11452)
