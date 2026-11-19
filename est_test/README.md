# NIST SP800-90B 熵评估测试工具

基于 [NIST SP800-90B](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-90B.pdf) 标准实现的熵源评估工具，支持 **Restart**、**IID** 和 **Non-IID** 三类测试模式，提供统一的命令行接口。

---

## 环境要求

- 建议 Python 3.12；解释器选择与完整依赖安装见[根 README](../README.md#2-环境)

---

## 目录结构

```
est_test/
├── est_test.py                    # 统一测试入口脚本（基于 est_core）
└── README.md                      # 本说明文档
```

核心算法模块位于上级目录 `est_core/` 中。

---

## 使用方法

以下直接调用的示例在 `est_test/` 目录执行，并使用已安装依赖的 Python：

```bash
python est_test.py -f <数据文件路径> [选项]
```

从仓库根目录也可使用 Make 目标（相对数据路径按根目录解析）：

```bash
make run_test TEST_ARGS="-f data/source.bin -b 8 --iid"
```

不传 `TEST_ARGS` 时默认显示帮助；该入口与重写版的参数格式不同，不能省略 `-f`。

---

## 参数说明

#### 基础参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--file` | `-f` | 待测试的二进制数据文件路径 | （必填） |
| `--bits_per_symbol` | `-b` | 每个样本符号所占的比特数 | `8` |
| `--verbose` | `-v` | 输出详细的内部测试过程信息 | 关闭 |

#### 测试模式选项（至少选择一项）

| 参数 | 说明 |
|------|------|
| `--restart` | 执行 Restart 重启状态完整性检验 |
| `--iid` | 执行 IID（独立同分布）检验及熵评估 |
| `--non-iid` | 执行 Non-IID 保守最小熵综合评估 |

#### 特定测试的高级参数

| 参数 | 适用模式 | 说明 |
|------|----------|------|
| `--use-bits` | Non-IID | 指定提取每个样本的低 N 位比特进行测试（不指定时默认等于 `bits_per_symbol`） |
| `--h-i` | Restart | 需要验证的目标初始最小熵估计值 H_I（执行 Restart 测试时**必须**指定） |

---

## 使用示例

#### 1. 执行 Restart 测试（需提供初始熵估计值）

```bash
python est_test.py -f source_out.bin -b 8 --restart --h-i 0.95 -v
```

#### 2. 仅执行 IID 测试

```bash
python est_test.py -f source_out.bin -b 8 --iid
```

#### 3. 执行 Non-IID 测试，仅使用低 4 位比特

```bash
python est_test.py -f source_out.bin -b 8 --non-iid --use-bits 4 -v
```

---

## 输出说明

- 测试过程中会在控制台输出各阶段的执行进度与中间结果（使用 `-v` 开启详细输出）。
- 所有测试完成后，以 **JSON 格式** 输出汇总结果，便于日志记录与二次集成处理。
- 若某项测试发生异常，错误信息会单独记录在 JSON 结果中，不会中断其他测试的执行。
- 完成后的退出码 0 不代表所有统计检验通过，需检查各测试返回的 `passed` / `IID` 等结果字段。

输出示例：

```json
{
    "Restart_Test": {},
    "IID_Test": {},
    "Non_IID_Test": {}
}
```

---

## 数据文件要求

- 数据文件必须为**二进制格式**。
- 每个 1～8 位样本单独占一个字节；`est_core/util.py` 的读取转换不支持大于 8 位的样本。
- 按 bit 打包的文件先用上级 `est_core_nist_cpp_recode/cli/ea_unpack_bits.py` 展开。
- IID / Non-IID 建议不少于 **1,000,000** 个连续样本；Restart 必须恰好 **1,000,000** 个，按 1000 × 1000 排列。
