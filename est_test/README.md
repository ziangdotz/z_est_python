# NIST SP800-90B 熵评估测试工具

基于 [NIST SP800-90B](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-90B.pdf) 标准实现的熵源评估工具，支持 **Restart**、**IID** 和 **Non-IID** 三类测试模式，提供统一的命令行接口。

---

## 环境要求

- Python 3.x

---

## 目录结构

```
est_test/
├── est_test.py          # 统一测试入口脚本
└── README.md            # 本说明文档
```

核心算法模块位于上级目录 `est_core/` 中，由 `est_test.py` 动态引入。

---

## 使用方法

基本语法：

```bash
python est_test.py -f <数据文件路径> [选项]
```

---

## 参数说明

### 基础参数（必填）

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--file` | `-f` | 待测试的二进制数据文件路径 | （必填） |
| `--bits_per_symbol` | `-b` | 每个样本符号所占的比特数 | `8` |
| `--verbose` | `-v` | 输出详细的内部测试过程信息 | 关闭 |

### 测试模式选项（至少选择一项）

| 参数 | 说明 |
|------|------|
| `--restart` | 执行 Restart 重启状态完整性检验 |
| `--iid` | 执行 IID（独立同分布）检验及熵评估 |
| `--non-iid` | 执行 Non-IID 保守最小熵综合评估 |

### 特定测试的高级参数

| 参数 | 适用模式 | 说明 |
|------|----------|------|
| `--use-bits` | Non-IID | 指定提取每个样本的低 N 位比特进行测试（不指定时默认等于 `bits_per_symbol`） |
| `--h-i` | Restart | 需要验证的目标初始最小熵估计值 H_I（执行 Restart 测试时**必须**指定） |

---

## 使用示例

### 1. 执行 Restart 测试（需提供初始熵估计值）

```bash
python est_test.py -f source_out.bin -b 8 --restart --h-i 0.95 -v
```

### 2. 仅执行 IID 测试

```bash
python est_test.py -f source_out.bin -b 8 --iid
```

### 3. 执行 Non-IID 测试，仅使用低 4 位比特

```bash
python est_test.py -f source_out.bin -b 8 --non-iid --use-bits 4 -v
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
