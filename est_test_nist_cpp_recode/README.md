# NIST SP800-90B 熵评估测试工具 — C++ Recode 版

基于 [NIST SP800-90B](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-90B.pdf) 标准实现的熵源评估工具（C++ v1.1.8 Python 重写版），支持 **Restart**、**IID** 和 **Non-IID** 三类测试模式。

---

## 环境要求

- Python 3.x
- NumPy
- （可选）SciPy（用于 χ² 检验，无时回退到内置实现）

---

## 目录结构

```
est_test_nist_cpp_recode/
├── est_test_nist_cpp_recode.py    # 统一测试入口脚本（基于 est_core_nist_cpp_recode）
└── README.md                      # 本说明文档
```

核心算法模块位于上级目录 `est_core_nist_cpp_recode/` 中。

---

## 使用方法

基本语法：

```bash
python est_test_nist_cpp_recode.py <数据文件路径> [选项]
```

---

## 参数说明

### 基础参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `datafile` | （位置参数） | 待测试的二进制数据文件路径 | （必填） |
| `--bits` | | 每个符号的位数（0 = 自动检测） | `0` |
| `--verbose` | `-v` | 增加输出详细程度（可叠加：`-v`, `-vv`） | `1` |

### 测试模式选项（至少选择一项）

| 参数 | 说明 |
|------|------|
| `--restart` | 执行 Restart 重启状态完整性检验 |
| `--iid` | 执行 IID（独立同分布）检验及熵评估 |
| `--non-iid` | 执行 Non-IID 保守最小熵综合评估 |

### 特定测试的高级参数

| 参数 | 适用模式 | 说明 |
|------|----------|------|
| `--h-i` | Restart | 需要验证的目标初始最小熵估计值 H_I（执行 Restart 测试时**必须**指定） |

---

## 使用示例

### 1. 执行 Restart 测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --restart --h-i 0.95 -v
```

### 2. 仅执行 IID 测试（自动检测符号位宽）

```bash
python est_test_nist_cpp_recode.py source_out.bin --iid
```

### 3. 指定 8 位符号执行 Non-IID 测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --bits 8 --non-iid -v
```

### 4. 同时执行三项测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --restart --iid --non-iid --h-i 0.95 -v
```

---

## 输出说明

- 测试过程中会在控制台输出各阶段的执行进度与中间结果（使用 `-v` 开启详细输出）。
- 所有测试完成后，以 **JSON 格式** 输出汇总结果，便于日志记录与二次集成处理。
- 若某项测试发生异常，错误信息会单独记录在 JSON 结果中，不会中断其他测试的执行。

输出示例：

```json
{
    "Restart_Test": { ... },
    "IID_Test": { ... },
    "Non_IID_Test": { ... }
}
```

---

## 数据文件要求

- 数据文件必须为**二进制格式**。
- 若熵源输出 1~8 位样本，每个样本单独占一个字节；若为 9~16 位，使用两个连续字节表示（高字节在前），依此类推。
- 建议采集不少于 **1,000,000** 个连续样本；若无法满足，请记录原因。
