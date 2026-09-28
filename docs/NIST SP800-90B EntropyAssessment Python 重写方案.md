# NIST SP800-90B EntropyAssessment Python 重写方案

> **目标**：将 NIST SP 800-90B 的 C++ 参考实现完整、准确、优化地重写为 Python。
> **C++ 版本**：v1.1.8 | 参考文档：`NIST SP800-90B_EntropyAssessment 实现分析.md`
> **Python 版本**：暂定 v1.0.1 | 许可证：保留 NIST 原有公共领域声明

---

## 目录

1. [总体架构](#1-总体架构)
2. [模块划分与依赖关系](#2-模块划分与依赖关系)
3. [数据结构设计](#3-数据结构设计)
4. [文件 I/O 与符号映射](#4-文件-io-与符号映射)
5. [随机数生成器](#5-随机数生成器)
6. [共享工具函数](#6-共享工具函数)
7. [Numerics 策略与精度方案](#7-numerics-策略与精度方案)
8. [IID 测试模块](#8-iid-测试模块)
9. [Non-IID 测试模块](#9-non-iid-测试模块)
10. [Prediction Estimate 框架](#10-prediction-estimate-框架)
11. [Restart 测试模块](#11-restart-测试模块)
12. [Conditioning 模块](#12-conditioning-模块)
13. [主入口与 CLI](#13-主入口与-cli)
14. [性能加速策略](#14-性能加速策略)
15. [测试与验证](#15-测试与验证)
16. [依赖清单](#16-依赖清单)
17. [实现路线图](#17-实现路线图)

---

## 1. 总体架构

### 目录结构

```
est_core_nist_cpp_recode/
├── ea/                         # 主包
│   ├── __init__.py
│   │
│   ├── _config.py              # 全局常量
│   │   # MIN_SIZE=1000000, PERMS=10000, ZALPHA=2.5758..., ITERMAX=1076
│   │   # D_LAG=128, LAGMASK=0x7F, D_MMC=16, B_len=16
│   │   # MAX_DICTIONARY_SIZE=65536, MAX_ENTRIES=100000
│   │   # NUM_WINS=4, W=[63,255,1023,4095], DEFAULT_SIM_ROUNDS=5000000
│   │   # SAINDEX_MAX = 2**31-1 (定义但未使用)
│   │   # DBL_EPSILON, DBL_MIN, NUM_TESTS=19
│   │
│   ├── _types.py               # 数据结构定义
│   │   # DataT, TestCaseBase, IidTestCase, NonIidTestCase
│   │   # PermutationTestResult, TestRunBase, IidTestRun, NonIidTestRun
│   │   # PostfixDictionary（没有 LagBuffer，见 §3.8）
│   │
│   ├── _io.py                  # 文件 I/O 与符号映射
│   │   # read_file(), read_file_subset(), free_data()
│   │
│   ├── _rng.py                 # PRNG: xoshiro256**
│   │   # Xoshiro256StarStar, seed(), random_range64(), random_unit()
│   │   # fy_shuffle(), xoshiro_jump(), create_parallel_rngs() (未调用)
│   │
│   ├── _util.py                # 工具函数
│   │   # calc_stats, calc_proportions, calc_counts
│   │   # n_choose_2, substr, fast_substr, max_vector, divide
│   │   # rel_epsilon_equal, compressed_bit_symbols
│   │   # prediction_estimate_function (66 次迭代), calc_p_local
│   │   # prediction_estimate, kahan_add
│   │
│   ├── _lrs.py                 # 后缀数组 + t-Tuple + LRS
│   │   # len_lrs_test(), sa_algs()
│   │   # NumPy 向量化前缀倍增 (每轮一次 argsort)，未使用 libdivsufsort
│   │
│   ├── chi_square.py           # χ² 独立性/拟合优度检验
│   │   # chi_square_tests(), chi_square_pvalue()
│   │   # scipy.special.gammaincc (优先) + 内置 _cephes_igamc (回退)
│   │
│   ├── permutation.py          # 19 项置换检验（轮次多进程并行，计数仍按轮序）
│   │   # permutation_tests(), run_tests()
│   │
│   ├── mcv.py                  # 6.3.1 Most Common Value
│   ├── collision.py            # 6.3.2 Collision Estimate
│   ├── markov.py               # 6.3.3 Markov Estimate
│   ├── compression.py          # 6.3.4 Compression Estimate
│   ├── multi_mcw.py            # 6.3.7 MultiMCW
│   ├── lag_test.py             # 6.3.8 Lag Prediction
│   ├── multi_mmc.py            # 6.3.9 MultiMMC
│   ├── lz78y.py                # 6.3.10 LZ78Y
│   │
│   ├── iid_pipeline.py         # IID 主流程
│   ├── non_iid_pipeline.py     # Non-IID 主流程
│   ├── restart.py              # Restart 测试
│   └── conditioning.py         # Conditioning 评估
│
└── cli/                        # CLI 入口
    ├── __init__.py
    ├── ea_restart.py           # 对应 ea_restart
    ├── ea_iid.py               # 对应 ea_iid
    ├── ea_non_iid.py           # 对应 ea_non_iid
    ├── ea_conditioning.py      # 对应 ea_conditioning
    └── ea_transpose.py         # 对应 ea_transpose (1000x1000 字节转置工具)
```

### 运行时数据流

```
原始二进制文件
    │
    ▼
read_file() / read_file_subset()
    │  ┌─ symbols (uint8[], mapped)
    │  ├─ rawsymbols (uint8[], original)
    │  ├─ bsymbols (uint8[], bit-expanded, each 0或1)
    │  ├─ word_size, alph_size, len, blen
    ▼
calc_stats() → rawmean, median
    │
    ├── IID 路径
    │   ├── chi_square_tests()       → pass/fail
    │   ├── len_lrs_test()           → pass/fail
    │   ├── mcv() on symbols         → H_original
    │   ├── mcv() on bsymbols        → H_bitstring
    │   └── permutation_tests()      → pass/fail + 3×19 矩阵
    │
    ├── Non-IID 路径
    │   ├── mcv()                    → H_original / H_bitstring
    │   ├── collision_test()         → H_bitstring (binary only)
    │   ├── markov_test()            → H_bitstring (binary only)
    │   ├── compression_test()       → H_bitstring (binary only)
    │   ├── sa_algs()                → t_tuple + LRS (both)
    │   ├── multi_mcw_test()         → prediction (both)
    │   ├── lag_test()               → prediction (both)
    │   ├── multi_mmc_test()         → prediction (both)
    │   ├── lz78y_test()             → prediction (both)
    │   └── h_assessed = min(H_original, word_size×H_bitstring)
    │
    └── Restart 路径
        ├── sanity_check()           → max_row_count, max_col_count
        ├── simulate_bound()         → X_cutoff (5M Monte Carlo)
        └── validation_test()        → min(H_r, H_c, H_I)
```

---

## 2. 模块划分与依赖关系

```
                  ┌─────────────┐
                  │  _config.py  │ (常量)
                  └──────┬──────┘
                         │
            ┌────────────┴────────────────┐
            │        _types.py             │ (DataT, TestCase 等)
            └────────────┬────────────────┘
                         │
    ┌────────┬───────────┼───────────┬──────────────┐
    │        │           │           │              │
  _io.py  _rng.py   _util.py   chi_square.py  _lrs.py
    │        │           │           │              │
    │        └──────┬────┘           │              │
    │               │                │              │
    ├───────┬───────┼───────┬───────┼───────┬───────┘
    │       │       │       │       │       │
  mcv.py  collision.py  markov.py  compression.py
    │       │       │       │       │       │
    └───────┼───────┼───────┼───────┼───────┘
            │       │       │       │
    ┌───────┼───────┼───────┼───────┤
    │       │       │       │       │
multi_mcw.py  lag_test.py  multi_mmc.py  lz78y.py
    │       │       │       │       │
    ├───────┼───────┼───────┼───────┘
    │       │       │       │
    ▼       ▼       ▼       ▼
  iid_pipeline.py  non_iid_pipeline.py  restart.py  conditioning.py
    │       │       │       │
    ▼       ▼       ▼       ▼
  cli/ea_iid.py  cli/ea_non_iid.py  cli/ea_restart.py  cli/ea_conditioning.py
```

### 依赖方向规则

1. `_util.py` → `_config.py`, `_types.py`（基础）
2. `_rng.py` → `_config.py`（独立）
3. `_io.py` → `_types.py`, `_config.py`（文件读取）
4. `_lrs.py` → `_util.py`, `_config.py`, `_types.py`
5. `chi_square.py` → `_util.py`, `_config.py`
6. `permutation.py` → `_types.py`, `_rng.py`, `_util.py`, `_config.py`
7. 各估计器 → `_types.py`, `_util.py`, `_config.py`（如果用到 prediction_estimate）
8. `*_pipeline.py` → 所有估计器
9. `cli/*` → 对应 pipeline

---

## 3. 数据结构设计

### 3.1 `DataT`（对应 C++ `data_t`）

```python
@dataclass
class DataT:
    word_size: int = 0          # bits per symbol (0 = auto-detect)
    alph_size: int = 0          # alphabet size after mapping
    maxsymbol: int = 0          # largest symbol in raw data
    rawsymbols: np.ndarray | None = None   # uint8, shape (len,)
    symbols: np.ndarray | None = None      # uint8, shape (len,)
    bsymbols: np.ndarray | None = None     # uint8, shape (blen,)  each 0 or 1
    len: int = 0                # number of symbols
    blen: int = 0               # number of bits (= len * word_size)
```

**设计决策**：
- 使用 `numpy.ndarray` 而非 Python `list`，因后续所有计算皆可受益于 numpy 向量化
- `bsymbols` 当 `word_size == 1` 时与 `symbols` 共享同一内存视图（如同 C++ 的指针赋值）

### 3.2 `TestCaseBase`（对应 C++ `TestCaseBase`）

```python
@dataclass
class TestCaseBase:
    h_original: float = -1.0
    h_bitstring: float = -1.0
    h_assessed: float = -1.0
    mcv_estimate_mode: float = -1.0
    mcv_estimate_p_hat: float = -1.0
    mcv_estimate_p_u: float = -1.0
    literal_mcv_estimate: bool = False
    ret_min_entropy: float = -1.0
    data_word_size: float = -1.0
    test_case_number: str = ""

    def to_dict(self) -> dict: ...
```

### 3.3 `IidTestCase`（对应 C++ `IidTestCase`）

```python
@dataclass
class IidTestCase(TestCaseBase):
    mean: float = 0.0
    median: float = 0.0
    binary: bool = False
    passed_chi_square_tests: bool = False
    passed_longest_repeated_substring_test: bool = False
    passed_iid_permutation_tests: bool = False
    h_r: float = -1.0
    h_c: float = -1.0
    h_i: float = -1.0
    test_results: list[PermutationTestResult] = field(default_factory=list)
```

### 3.4 `NonIidTestCase`（对应 C++ `NonIidTestCase`）

```python
@dataclass
class NonIidTestCase(TestCaseBase):
    bin_t_tuple_res: float = -1.0
    t_tuple_res: float = -1.0
    bin_lrs_res: float = -1.0
    lrs_res: float = -1.0
    h_r: float = -1.0
    h_c: float = -1.0
    h_i: float = -1.0
    n_in: float = -1.0
    n_out: float = -1.0
    nw: float = -1.0
    h_in: float = -1.0
    h_out: float = -1.0
    h_p: float = -1.0
```

### 3.5 `PermutationTestResult`（对应 C++ `PermutationTestResult`）

```python
@dataclass
class PermutationTestResult:
    iteration: int = -1
    excursion: float = -1.0
    num_directional_runs: float = -1.0
    len_directional_runs: float = -1.0
    num_increases_decreases: float = -1.0
    num_runs_median: float = -1.0
    len_runs_median: float = -1.0
    avg_collision: float = -1.0
    max_collision: float = -1.0
    periodicity1: float = -1.0
    periodicity2: float = -1.0
    periodicity8: float = -1.0
    periodicity16: float = -1.0
    periodicity32: float = -1.0
    covariance1: float = -1.0
    covariance2: float = -1.0
    covariance8: float = -1.0
    covariance16: float = -1.0
    covariance32: float = -1.0
    compression: float = -1.0
```

### 3.6 `TestRunBase` / `IidTestRun` / `NonIidTestRun`

用字典结构（dict-based）而非类继承，输出 JSON 更灵活：

```python
@dataclass
class TestRunBase:
    timestamp: str = ""
    sha256: str = ""
    filename: str = ""
    error_level: int = 0
    error_msg: str = ""
    type: str = ""
    commandline: str = ""

    def to_dict(self) -> dict: ...

@dataclass
class IidTestRun(TestRunBase):
    iid: bool = True
    test_cases: list[IidTestCase] = field(default_factory=list)

@dataclass
class NonIidTestRun(TestRunBase):
    iid: bool = False
    test_cases: list[NonIidTestCase] = field(default_factory=list)
```

### 3.7 `PostfixDictionary`（对应 C++ `PostfixDictionary`）

```python
class PostfixDictionary:
    """用于 LZ78Y 和 MultiMMC 的 (prefix → postfix count) 映射"""
    _postfixes: dict[int, int]  # postfix → count
    _cur_best: int              # 当前最高计数
    _cur_prediction: int        # 最高计数对应的 postfix

    def predict(self) -> tuple[int, int]:
        """返回 (count, prediction)"""
        ...

    def increment_postfix(self, postfix: int, make_new: bool) -> bool:
        """递增 postfix 计数。返回 True 如果新建了条目"""
        ...
```

### 3.8 Lag 预测的窗口结构（没有 `LagBuffer` 类）

本文档早先在这里描述过一个 `LagBuffer` dataclass（`start` / `end` / `buf=[0]*128`，并称 128 是
硬编码、不走 `_config.D_LAG`）。**那个类不存在**——全仓 Python 代码里 `LagBuffer` 零引用，
`_types.py` 的实际成员是 `DataT` / `TestCaseBase` / `IidTestCase` / `NonIidTestCase` /
`PermutationTestResult` / `TestRunBase` / `IidTestRun` / `NonIidTestRun` / `PostfixDictionary`。

`ea/lag_test.py` 用的是两套等价写法，且 `D_LAG` 是**从 `_config` 导入**的（`lag_test.py:9`），
不是硬编码：

- **CPython 侧**：每个符号一条**升序出现位置列表** `seen`，用 `bisect_left(seen, cutoff)`
  裁掉窗口外的旧位置（`lag_test.py:5,61`）。不需要环形缓冲的理由写在模块 docstring 里：
  游走最多只会停在最近 `D_LAG` 个样本内，所以环里不可能存在「窗口过滤会保留、而环已丢弃」的项。
- **numba kernel 侧**：逐字照搬参考实现的 `lagBuf`——一个 `(alph_size, D_LAG)` 的 int64
  numpy 环（`lag_test.py:94,123,133`）。

两侧的原始计数由 `jit_crosscheck.py` 对拍，所以这一处同时也是「数据结构对译」的验证点
（见 `est_test_nist_cpp_recode/README.md`）。改 `D_LAG` 只需改 `_config.py`。

---

## 4. 文件 I/O 与符号映射

### 4.1 `read_file()` / `read_file_subset()`

```python
def read_file(
    file_path: str,
    dp: DataT,
    test_run: TestRunBase | None = None
) -> bool: ...

def read_file_subset(
    file_path: str,
    dp: DataT,
    subset_index: int,
    subset_size: int,
    test_run: TestRunBase | None = None
) -> bool: ...
```

**关键实现细节**：

1. **打开文件**：使用 `open(file_path, 'rb')`
2. **检测文件大小**：`os.path.getsize()` 或 `f.seek(0, 2)` + `f.tell()`
3. **子集定位**：如果是 subset reading，`f.seek(subset_index * subset_size)`
4. **读取**：`f.read()` → `bytearray` → `numpy.frombuffer(..., dtype=np.uint8)`
5. **自动检测 word_size**：
   ```python
   def _detect_word_size(symbols: np.ndarray) -> int:
       datamask = 0
       for b in symbols:
           datamask |= int(b)
       curbit = 0x80
       i = 8
       while i > 0 and (datamask & curbit) == 0:
           curbit >>= 1
           i -= 1
       return i

   if dp.word_size == 0:
       dp.word_size = _detect_word_size(dp.symbols)
   ```
6. **验证 word_size**：
   - 如果实际所需位数 < 用户指定的 word_size → warning
   - 如果 > → error
7. **符号映射**：
   ```python
   dp.rawsymbols = dp.symbols.copy()  # 保存原始数据
   dp.maxsymbol = int(np.max(dp.symbols))
   max_symbols = 1 << dp.word_size
   mask = max_symbols - 1
   dp.symbols = dp.symbols & mask  # 先应用掩码
   dp.maxsymbol = int(np.max(dp.symbols))
   unique_vals = np.unique(dp.symbols)
   dp.alph_size = len(unique_vals)
   symbol_map = np.zeros(max_symbols, dtype=np.int32)
   for new_idx, val in enumerate(unique_vals):
       symbol_map[val] = new_idx
   dp.symbols = symbol_map[dp.symbols].astype(np.uint8)  # 映射到连续索引
   ```
8. **构建 bsymbols**（实际实现已用 `np.unpackbits` 向量化，无 Python 循环）：
   ```python
   dp.blen = dp.len * dp.word_size
   if dp.word_size == 1:
       dp.bsymbols = dp.symbols  # 共享视图
   else:
       # unpackbits() 每字节按 MSB-first 展开，所以一个符号的低 word_size 位
       # 就是每行的末尾 word_size 列
       bits = np.unpackbits(dp.rawsymbols, bitorder='big').reshape(dp.len, 8)
       dp.bsymbols = np.ascontiguousarray(bits[:, 8 - dp.word_size:]).reshape(-1)
   ```
   > 本节早先描述的是一个逐符号逐位的 Python 双重循环（`for i in range(dp.len): for j in
   > range(dp.word_size): ...`），那版已被替换——1M 样本 × word_size 次迭代的开销没有了。

### 4.2 `free_data()`

```python
def free_data(dp: DataT) -> None:
    """释放 DataT 中持有的 numpy 数组"""
    dp.rawsymbols = None
    dp.symbols = None
    if dp.word_size > 1:
        dp.bsymbols = None
```

---

## 5. 随机数生成器

### 5.1 `Xoshiro256StarStar` 类

```python
class Xoshiro256StarStar:
    """xoshiro256** 1.0 by Blackman & Vigna"""
    _state: np.ndarray  # uint64[4]

    def __init__(self, seed: np.ndarray | None = None):
        if seed is None:
            self.seed()          # 从 os.urandom(32) 构建
        else:
            self._state = seed.copy()

    def next(self) -> int:        # → uint64
        """返回 64 位随机数，更新状态"""
        ...

    def jump(self, count: int = 1):
        """等价于 count * 2^128 次 next() 调用"""
        ...

    def random_range64(self, s: int) -> int:
        """Lemire 算法：返回 [0, s] 均匀分布，无模数偏差"""
        ...

    def random_unit(self) -> float:
        """返回 [0, 1) 均匀分布的 float64"""
        return (self.next() >> 11) * 0x1.0p-53

    def fy_shuffle(self, data: np.ndarray, rawdata: np.ndarray):
        """Fisher-Yates 原地洗牌：同时对 data 和 rawdata 做相同的置换"""
        ...
```

**种子**：`os.urandom(32)` → `numpy.frombuffer(..., dtype=np.uint64)`，4 个 uint64

**`seed()` 的跨平台替代**：因为 Python 没有 `/dev/urandom` 不可用的问题（`os.urandom` 在所有平台都可用），不需要 C++ 的错误处理逻辑。

### 5.2 静态函数

```python
def random_range64(s: int, rng: Xoshiro256StarStar) -> int: ...

def random_unit(rng: Xoshiro256StarStar) -> float: ...

def fy_shuffle(data: np.ndarray, rawdata: np.ndarray, rng: Xoshiro256StarStar): ...
```

### 5.3 并行支持

置换检验的轮次并行不使用 `Xoshiro256StarStar.jump()`，而是改用 numpy 的
`SeedSequence`：每一轮用自己的下标重新派生一条独立随机流，因此某一轮的置换
只取决于轮次号，与轮次如何分配到进程无关（同一 seed 下 worker 数任意变化，
`C` 矩阵逐元素一致）。

```python
def _round_statistics(dp, rawmean, median, seed, round_index, test_status) -> np.ndarray:
    """第 round_index 轮的 19 项统计量；shuffle 由 SeedSequence([seed, round_index]) 驱动"""
    rng = np.random.default_rng(np.random.SeedSequence([seed, round_index]))
    perm = random_permutation(dp.len, rng)
    return run_tests(dp, dp.symbols[perm], dp.rawsymbols[perm], rawmean, median, test_status)
```

`rng="xoshiro"`（与参考实现逐位一致的 Fisher-Yates）保持串行：它的 shuffle 把自身
状态带入下一轮，第 `i` 轮无法在第 `i - 1` 轮之前产出。

---

## 6. 共享工具函数

所有工具函数位于 `ea/_util.py`：

| 函数 | 签名 | 备注 |
|------|------|------|
| `calc_stats` | `(dp: DataT) -> tuple[float, float]` | 返回 rawmean, median。binary 时 median 固定 0.5 |
| `calc_proportions` | `(data: np.ndarray, p: np.ndarray)` | p 就地修改 |
| `calc_counts` | `(data: np.ndarray, c: np.ndarray)` | c 就地修改 |
| `n_choose_2` | `(n: int) -> int` | n*(n-1)//2 |
| `substr` | `(text, pos, len, total) -> np.ndarray` | 安全截取 |
| `fast_substr` | `(text, pos, len) -> np.ndarray` | 无边界检查，固定 16 字节 |
| `max_vector` | `(v) -> T` | 泛型最大值 |
| `divide` | `(a, b) -> float` | a / b |
| `rel_epsilon_equal` | `(A, B, ...) -> bool` | Knuth 风格的浮点近似比较 |
| `compressed_bit_symbols` | `(S, length) -> int` | ≤32 位符号压缩为 uint32 |
| `prediction_estimate_function` | `(p, r, N) -> float` | 预测估计目标函数 (66 次迭代) |
| `calc_p_local` | `(max_run_len, N, ldomain) -> float` | 二分搜索 p_local |
| `prediction_estimate` | `(C, N, max_run_len, k, ...) -> float` | 统一预测估计入口 |
| `kahan_add` | `(sum, comp, inp)` | Kahan 求和累加 |

### `rel_epsilon_equal` 实现策略

```python
def rel_epsilon_equal(
    A: float, B: float,
    max_abs_factor: float = DBL_EPSILON,
    max_rel_factor: float = DBL_EPSILON,
    max_ulp: int = 4
) -> bool:
    """C++ relEpsilonEqual 的精确 Python 翻译"""
    # 1. NaN → False
    # 2. 精确相等 → True
    # 3. Infinity 但不等 → False
    # 4. 绝对值小的作 A，大的作 B
    # 5. subnormal → 绝对比较
    # 6. 正常 → 相对比较
    # 7. ULP 比较 (使用 struct.pack/struct.unpack 访问 IEEE 754 位模式)
```

**关键**：Python 的 `float` 是 IEEE 754 double，可以通过 `struct.pack('>d', f)` 获取位表示。

### `prediction_estimate_function` 的精度策略

```python
def prediction_estimate_function(p: float, r: int, N: int) -> float:
    """
    返回 log(1-p*x) - log((r+1-r*x)*q) - (N+1)*log(x)
    其中 q=1-p, x 通过迭代求解 x_{i+1} = 1 + q*p^r * x_i^(r+1)
    """
    q = 1.0 - p
    x = 1.0
    x_last = 0.0
    for i in range(66):
        if (x - x_last) <= (DBL_EPSILON * x):
            break
        x_last = x
        x = 1.0 + q * (p ** r) * (x ** (r + 1.0))
    return math.log(1.0 - p * x) - math.log((r + 1.0 - r * x) * q) - (N + 1.0) * math.log(x)
```

**精度考量**：C++ 用 `long double` (80-bit)，Python 用 `float` (53-bit)，差异可能影响二分搜索的收敛路径。如果测试偏差超过 1e-6，需切换到 `mpmath.mpf`：

```python
def prediction_estimate_function_mp(p, r, N, prec=64):
    mp.mp.dps = prec
    p = mp.mpf(p)
    ...
```

---

## 7. Numerics 策略与精度方案

### 7.1 精度分层

| 模块 | C++ 精度 | Python 方案 | 预期偏差 |
|------|---------|------------|---------|
| MCV | `double` | `float` | < 1e-15 |
| Collision | `double` | `float` | < 1e-15 |
| Markov | `double` + `log2` | `float` + `math.log2` | < 1e-12 |
| Compression G() | `double` + Kahan | `float` + Kahan | < 1e-10 |
| t-Tuple (Q 数组) | `long double` + `powl` | `float` + `math.pow` | < 1e-10 |
| LRS | `long double` + `powl` | `float` + `math.pow` | < 1e-10 |
| Prediction Estimate | `long double` + `powl` + `logl` | `mpmath` (默认 64-bit, 可自动提升) | < 1e-12 |
| Prediction objective | `long double` 迭代 | `mpmath` 或 `float`+早期终止 | < 1e-10 |
| Conditioning | MPFR 任意精度 | `mpmath` + `decimal.Decimal` | exact |
| Restart simulation | `uint16_t` | `int` (Python 原生) | exact |

### 7.2 实际精度方案

**实际实现中**：Prediction Estimate 未使用 `mpmath`，而是全部使用标准 Python `float`（IEEE 754 double）。

```python
# _util.py 实际使用 math.log / math.pow / math.sqrt（标准 float）
# prediction_estimate_function 使用 66 次迭代 + DBL_EPSILON 早期终止
# calc_p_local 使用二分搜索 + rel_epsilon_equal ULP 比较终止
```

`mpmath` 仅在 Conditioning 模块（`conditioning.py`）中使用，用于 Section 3.1.5.1.2 的任意精度计算。

### 7.3 组合计数的大整数安全

C++ 的 `uint128_t` 在 Python 中不需要 — Python 整数无上限：

```python
# C++: choices = ((uint64_t)(A[t]+1) * (uint64_t)(A[t])) >> 1
# Python:
choices = (A_t + 1) * A_t // 2   # 直接安全
```

### 7.4 Cephes 函数的 Python 替代

| Cephes 函数 | Python 替代 |
|-------------|------------|
| `cephes_igamc(a, x)` | `scipy.special.gammaincc(a, x)` |
| `cephes_lgam(x)` | `math.lgamma(x)` |
| `sig` | Python 标准 `math.lgamma` 处理 |

```python
from scipy.special import gammaincc

def chi_square_pvalue(x: float, k: int) -> float:
    """Pearson χ² p-value: Q(k/2, x/2)"""
    return float(gammaincc(k / 2.0, x / 2.0))
```

**实际实现**：`chi_square.py` 使用 try/except 导入 scipy，失败时回退到内置 `_cephes_igamc` 函数。scipy 是可选依赖。

### 7.5 Kahan 求和

```python
def kahan_add(sum: float, comp: float, inp: float) -> tuple[float, float]:
    """Kahan 补偿求和。返回 (new_sum, new_comp)"""
    y = inp - comp
    t = sum + y
    comp = (t - sum) - y
    return t, comp
```

---

## 8. IID 测试模块

### 8.1 χ² 独立性检验

**函数签名**：
```python
def chi_square_independence(
    data: np.ndarray, sample_size: int, alphabet_size: int
) -> tuple[float, int]: ...
def binary_chi_square_independence(
    data: np.ndarray, sample_size: int
) -> tuple[float, int]: ...
```

**实现注意**：
- 合并期望小于 5 的 bin（与 C++ 完全一致的合并策略：排序 → 累积 ≥5 → 不足 5 则合并到最后两个 bin）
- `__builtin_popcount` → Python `int.bit_count()`（3.8+）

### 8.2 χ² 拟合优度检验

```python
def binary_goodness_of_fit(
    data: np.ndarray, sample_size: int
) -> tuple[float, int]: ...

def goodness_of_fit(
    data: np.ndarray, sample_size: int, alphabet_size: int
) -> tuple[float, int]: ...
```

### 8.3 综合 χ² 测试

```python
def chi_square_tests(
    data: np.ndarray, sample_size: int, alphabet_size: int, verbose: int = 0
) -> bool:
    """返回 True 若两项测试均通过"""
    # independence test
    if alphabet_size == 2:
        score, df = binary_chi_square_independence(data, sample_size)
    else:
        score, df = chi_square_independence(data, sample_size, alphabet_size)
    pvalue = chi_square_pvalue(score, df)
    passed = pvalue >= 0.001

    # goodness of fit test
    if alphabet_size == 2:
        score, df = binary_goodness_of_fit(data, sample_size)
    else:
        score, df = goodness_of_fit(data, sample_size, alphabet_size)
    pvalue = chi_square_pvalue(score, df)
    passed = passed and (pvalue >= 0.001)

    return passed
```

### 8.4 19 项置换检验

**函数签名**：
```python
def run_tests(
    dp: DataT,
    data: np.ndarray,
    rawdata: np.ndarray,
    rawmean: float,
    median: float,
    test_status: list[bool]
) -> np.ndarray:  # shape (19,) float64
```

**独立测试函数**：

| 函数 | 参数 | 返回 |
|------|------|------|
| `excursion(data, rawmean, n)` | rawdata | max deviation |
| `alt_sequence1(data, n)` | symbols | diff signs |
| `alt_sequence2(data, median, n)` | symbols | median signs |
| `num_directional_runs(alt_seq)` | alt_seq | count |
| `len_directional_runs(alt_seq)` | alt_seq | max length |
| `num_increases_decreases(alt_seq)` | alt_seq | max(pos, neg) |
| `find_collisions(data, n, k)` | symbols | collision lengths |
| `avg_collision(col_seq)` | collision seq | mean |
| `max_collision(col_seq)` | collision seq | max |
| `periodicity(data, p, n)` | data | match count |
| `covariance(data, p, n)` | data | sum product |
| `compression(data, n, max_symbol)` | rawsymbols | compressed size |

**Conversion 函数**：

```python
def conversion1(data: np.ndarray, n: int) -> np.ndarray:
    """二进制数据：8-bit 分组，每组数 1 的个数"""
    ...

def conversion2(data: np.ndarray, n: int) -> np.ndarray:
    """二进制数据：8-bit 分组，解释为字节"""
    ...
```

**置换循环**：

```python
def permutation_tests(dp: DataT, rawmean: float, median: float,
                      verbose: int, tc: IidTestCase,
                      rng: str = "numpy",
                      seed: Optional[int] = None,
                      num_workers: Optional[int] = None) -> bool:
    C = np.zeros((NUM_TESTS, 3), dtype=np.int64)
    test_status = np.ones(NUM_TESTS, dtype=bool)

    # 初始（未置换）运行，同时得到单轮成本的初值
    t = run_tests(dp, dp.symbols, dp.rawsymbols, rawmean, median, test_status)

    # 轮次由 ProcessPoolExecutor 按批次预先产出（每批时长目标 _TASK_BUDGET=0.10 s），
    # 主进程按轮序重放计数；window = workers，保证 worker 不空转
    while pending or submitted < PERMS:
        ...
```

**实际状态**：轮次已改为多进程并行（默认每个物理核 1 个，CLI `-j/--workers` 可覆盖），
计数与判定仍在主进程按轮序完成，并行结果与同 seed 串行逐元素一致。仍然存在的限制：
内存带宽/频率墙钟使 1M 样本上的加速比在 3–5x 量级（而非线性），`rng="xoshiro"` 不并行。
进程池无法启动时（如冻结入口缺少 `freeze_support()`）会打印警告并退回单进程。

**早期终止**：当某个测试的 `C[j][0] + C[j][1] > 5` 且 `C[j][1] + C[j][2] > 5`，标记为 `test_status[j] = False` 并停止更新。当所有 19 项均终止时，停止该轮洗牌。

### 8.5 LRS 测试（IID）

```python
def len_lrs_test(
    data: np.ndarray, L: int, k: int, verbose: int = 0, label: str = ""
) -> bool:
    """返回 True 若 Pr(X >= 1) >= 0.001"""
    # 1. 计算 p_col = Σ p[i]²
    p = np.zeros(k)
    calc_proportions(data, p, L)
    p_col = np.sum(p ** 2)

    # 2. 构建后缀数组（调用 libdivsufsort 或 Python 实现）
    W = len_lrs(data, L)

    # 3. 计算概率
    p_col_power = p_col ** W
    log_prob_no_col_per_pair = math.log1p(-p_col_power)
    N = n_choose_2(L - W + 1)
    return math.log(0.999) >= N * log_prob_no_col_per_pair
```

---

## 9. Non-IID 测试模块

### 9.0 Non-IID JSON 输出结构与 C++ 对标关系

Python 重写覆盖了 NIST SP 800-90B Section 6.3 的全部 10 个估计器，无遗漏。

| Section | 名称 | C++ 函数 | Python 模块 | 已实现 |
|---------|------|---------|------------|--------|
| 6.3.1 | MCV | `most_common()` | `mcv.py` | ✓ |
| 6.3.2 | Collision | `collision_test()` | `collision.py` | ✓ |
| 6.3.3 | Markov | `markov_test()` | `markov.py` | ✓ |
| 6.3.4 | Compression | `compression_test()` | `compression.py` | ✓ |
| 6.3.5 | t-Tuple | `SAalgs()` | `_lrs.py` | ✓ |
| 6.3.6 | LRS | `SAalgs()` | `_lrs.py` | ✓ |
| 6.3.7 | MultiMCW | `multi_mcw_test()` | `multi_mcw.py` | ✓ |
| 6.3.8 | Lag | `lag_test()` | `lag_test.py` | ✓ |
| 6.3.9 | MultiMMC | `multi_mmc_test()` | `multi_mmc.py` | ✓ |
| 6.3.10 | LZ78Y | `LZ78Y_test()` | `lz78y.py` | ✓ |

#### C++ 官方 JSON 结构

`ea_non_iid` 输出 **11 个独立的测试用例** + 一个 "Overall" 汇总：

| 索引 | `testCaseDesc` | 输出字段 |
|------|---------------|---------|
| 1 | "Most Common Value" | `retMinEntropy`, `mcvEstimateMode/PHat/PU`, `hOriginal`, `hBitstring` |
| 2 | "Collision Test (for bit strings only)" | `hBitstring`, `hOriginal` (binary 时) |
| 3 | "Markov Test (for bit strings only)" | 同上 |
| 4 | "Compression Test (for bit strings only)" | 同上 |
| 5 | "T-Tuple Test" | `binTTupleRes`, `tTupleRes` |
| 6 | "LRS Test" | `binLrsRes`, `lrsRes` |
| 7 | "Multi Most Common in Window Test" | `hBitstring`, `hOriginal` |
| 8 | "Lag Prediction Test" | 同上 |
| 9 | "Multi Markov Model with Counting Test" | 同上 |
| 10 | "LZ78Y Test" | 同上 |
| **11** | **"Overall"** | **`hOriginal`, `hBitstring`, `hAssessed`, `dataWordSize`** |

各字段在 `TestCaseBase` / `NonIidTestCase` 中的定义：

```cpp
// TestCaseBase
double h_original = -1.0, h_bitstring = -1.0, h_assessed = -1.0;
double mcv_estimate_mode = -1.0, mcv_estimate_p_hat = -1.0, mcv_estimate_p_u = -1.0;
bool literal_mcv_estimate = false;
double ret_min_entropy = -1.0, data_word_size = -1.0;

// NonIidTestCase (extends TestCaseBase)
double bin_t_tuple_res = -1.0, t_tuple_res = -1.0;
double bin_lrs_res = -1.0, lrs_res = -1.0;
double h_r, h_c, h_i;          // Restart 验证用
double n_in, n_out, nw;        // Conditioning 用
double h_in, h_out, h_p;
```

#### Python 输出与 C++ 字段对标

Python 现在输出 **11 个独立的测试用例**，与 C++ 结构完全一致。每个 case 只包含对应字段：

| 索引 | Python `testCaseNumber` | 输出字段 |
|------|------------------------|---------|
| 1 | `"Most Common Value"` | `hOriginal`, `hBitstring`, `mcvEstimateMode/PHat/PU` |
| 2 | `"Collision Test (for bit strings only)"` | `hOriginal`, `hBitstring` (binary only) |
| 3 | `"Markov Test (for bit strings only)"` | 同上 |
| 4 | `"Compression Test (for bit strings only)"` | 同上 |
| 5 | `"T-Tuple Test"` | `tTupleRes`, `binTTupleRes` |
| 6 | `"LRS Test"` | `lrsRes`, `binLrsRes` |
| 7 | `"Multi Most Common in Window Test"` | `hOriginal`, `hBitstring` |
| 8 | `"Lag Prediction Test"` | 同上 |
| 9 | `"Multi Markov Model with Counting Test (MultiMMC)"` | 同上 |
| 10 | `"LZ78Y Test"` | 同上 |
| **11** | **`"Overall"`** | **`hOriginal`, `hBitstring`, `dataWordSize`, `hAssessed`** |

各字段的 JSON key 名与 C++ 一致（`hOriginal`, `hBitstring`, `hAssessed`, `dataWordSize`, `mcvEstimateMode`, `mcvEstimatePHat`, `mcvEstimatePU`, `binTTupleRes`, `tTupleRes`, `binLrsRes`, `lrsRes`）。

**差异已消除**：Python 现在输出 11 个独立的测试用例（结构、顺序、字段名与 C++ 完全一致）。字段值仅在计算后才设置（`!= -1.0` 时输出），非 binary 数据下 Cases 2-4 无对应字段（与 C++ 逻辑一致）。

#### 行为差异

Python 与 C++ 存在一个差异：
- **C++**：使用 `initial_entropy` 标志控制 symbol 和 bsymbol 测试的执行。当 `initial_entropy=true` 且 `alph_size == 2` 时，bsymbol 上的冗余计算被跳过（`symbols == bsymbols` 共享内存）
- **Python**：`run_non_iid_test()` 没有 `initial_entropy` 参数，始终同时计算 `symbols` 和 `bsymbols`。但 binary 下两者共享同一 `np.ndarray`，结果数值一致

最终 `h_assessed = min(h_original, word_size * h_bitstring)` 在两种实现中给出相同数值。

### 9.1 MCV — `ea/mcv.py`

```python
def most_common_value(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = "",
    tc: TestCaseBase | None = None
) -> float:
    """Section 6.3.1: 返回 min-entropy = -log2(p_u)"""
    # 直方图只统计前 length 个样本：调用方可能递来比待评估数据更长的缓冲区
    # （`-t` 会截断位串），统计整个数组就会算错
    counts = np.bincount(np.ascontiguousarray(data[:length], dtype=np.int64), minlength=alph_size)
    mode = int(np.max(counts))
    pmax = mode / length
    pu = min(1.0, pmax + ZALPHA * math.sqrt(pmax * (1.0 - pmax) / (length - 1.0)))
    return -math.log2(pu)
```

**优化**：`np.bincount` 比 Python 循环快 10-100x

### 9.2 Collision — `ea/collision.py`

```python
def collision_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """Section 6.3.2: 二进制数据碰撞时间估计"""
    # 遍历：遇到 00/11 等待 2，遇到 01/10 等待 3
    i = 0
    v = 0
    sum_t = 0
    sum_t2 = 0.0
    while i < length - 1:
        if data[i] == data[i + 1]:
            t_v = 2
        elif i < length - 2:
            t_v = 3
        else:
            break
        v += 1
        sum_t += t_v
        sum_t2 += t_v * t_v
        i += t_v

    X_bar = sum_t / v
    sigma_hat = math.sqrt((sum_t2 - sum_t * X_bar) / (v - 1))
    X_prime = X_bar - ZALPHA * sigma_hat / math.sqrt(v)
    if X_prime < 2.0:        # 2.0 是最小有意义的等待时间
        X_prime = 2.0

    if X_prime < 2.5:
        p = 0.5 + math.sqrt(1.25 - 0.5 * X_prime)
        return -math.log2(p)
    else:
        return 1.0
```

**已修的保真缺陷**：`X_prime` 少了 `if (X < 2.0) X = 2.0;` 这一步夹紧。每个等待时间都是 2 或 3，
所以均值不可能低于 2.0，一旦低于就只能是置信下界冲过头；不夹紧会让 `p > 1.0`，`-log2(p)` 变成
**负的 min-entropy** 并污染 `H_bitstring`/`H_assessed`。11 个 refdata 样本的 `X-bar'` 都在 2.5 附近，
触发不了这条分支，因此只能靠构造用例暴露：对稀疏 1 位串（len 64–200、1 的个数 3–6）把参考实现的
`collision_test()` 逐字编成独立 exe 对拍，参考返回 `-0.0`，我们返回 -0.0011…-0.0366；补上夹紧后
6 个用例的返回值与 verbose 3 全部 8 行逐字相同，1,000,000 位的 `truerand_1bit.bin` 只剩
`min entropy` 末位 1 ULP（libm `log2` 差异）。

### 9.3 Markov — `ea/markov.py`

```python
def markov_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """Section 6.3.3: 二进制马尔可夫模型"""
    # c0/c1 只覆盖 S[0..length-2]：恰好是有后继的那些符号
    c0 = int(np.sum(data[:length-1] == 0))
    c1 = (length - 1) - c0
    c00 = int(np.sum((data[:length-1] == 0) & (data[1:length] == 0)))
    c10 = int(np.sum((data[:length-1] == 1) & (data[1:length] == 0)))

    if c0 > 0:
        p00, p01 = c00 / c0, 1 - c00 / c0
    else:
        p00 = p01 = 0.0
    if c1 > 0:
        p10, p11 = c10 / c1, 1 - c10 / c1
    else:
        p10 = p11 = 0.0

    # C++ 在算完转移概率之后才 “account for the last symbol”：把最后一个符号
    # 补进 c0 再算无条件概率，所以 P_0 跨 length 个样本而 P_01/P_10 跨 length-1 个
    if data[length - 1] == 0:
        c0 += 1
    p0 = c0 / length
    p1 = 1.0 - p0

    # 6 种序列长度评估
    h_min = 128.0

    def try_seq(h: float):
        nonlocal h_min
        if h < h_min:
            h_min = h

    if p00 > 0:
        try_seq(-math.log2(p0) - 127 * math.log2(p00))
    if p01 > 0 and p10 > 0:
        try_seq(-math.log2(p0) - 64 * math.log2(p01) - 63 * math.log2(p10))
    if p01 > 0 and p11 > 0:
        try_seq(-math.log2(p0) - math.log2(p01) - 126 * math.log2(p11))
    if p10 > 0 and p00 > 0:
        try_seq(-math.log2(p1) - math.log2(p10) - 126 * math.log2(p00))
    if p10 > 0 and p01 > 0:
        try_seq(-math.log2(p1) - 64 * math.log2(p10) - 63 * math.log2(p01))
    if p11 > 0:
        try_seq(-math.log2(p1) - 127 * math.log2(p11))

    return min(h_min / 128.0, 1.0)
```

### 9.4 Compression — `ea/compression.py`

```python
def _com_exp(p: float, alph_size: int, d: int, num_blocks: int) -> float:
    """
    Expected value of log2(gap) under geometric distribution with parameter p.
    G(z, d, num_blocks) function.
    """
    q = 1.0 - p
    max_k = num_blocks - d
    X_sum = 0.0
    X_comp = 0.0
    for k in range(1, max_k + 1):
        prob = p * (q ** (k - 1))
        log_val = math.log2(k) * prob
        X_sum, X_comp = kahan_add(X_sum, X_comp, log_val)
    return X_sum


def compression_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """Section 6.3.4: 基于 LZ 字典的压缩估计"""
    b = 6
    d = 1000
    alph_size = 1 << b
    num_blocks = length // b

    if num_blocks <= d:
        return -1.0

    # 构建字典 (6-bit 块)
    blocks = data[:num_blocks * b].reshape(-1, b)
    block_vals = np.zeros(num_blocks, dtype=np.int64)
    for i in range(num_blocks):
        val = 0
        for j in range(b):
            val |= int(blocks[i, j]) << (b - 1 - j)
        block_vals[i] = val

    dict_map = np.full(alph_size, -1, dtype=np.int64)
    for i in range(d):
        dict_map[block_vals[i]] = i + 1

    X_sum = 0.0
    X_comp = 0.0
    sigma_sum = 0.0
    sigma_comp = 0.0
    for i in range(d, num_blocks):
        log_val = math.log2(i + 1 - dict_map[block_vals[i]])
        X_sum, X_comp = kahan_add(X_sum, X_comp, log_val)
        sq = log_val * log_val
        sigma_sum, sigma_comp = kahan_add(sigma_sum, sigma_comp, sq)
        dict_map[block_vals[i]] = i + 1

    v = num_blocks - d
    X_bar = X_sum / v
    sigma_hat = 0.5907 * math.sqrt(sigma_sum / (v - 1.0) - X_bar * X_bar)
    X_prime = X_bar - ZALPHA * sigma_hat / math.sqrt(v)

    # 二分搜索 p
    if _com_exp(1.0 / alph_size, alph_size, d, num_blocks) > X_prime:
        p = _binary_search_p(X_prime, alph_size, d, num_blocks)
    else:
        p = -1.0

    if p > 1.0 / alph_size:
        return -math.log2(p) / b
    else:
        return 1.0
```

**Bug 修复 (2026-05-20)**：`_com_exp` 函数最初缺少几何分布的概算加权因子 `p * (1-p)^(k-1)`，仅计算了 `log2(k)` 的算术平均（约 15.9）。这导致二分搜索总是收敛到 `p=1`，进而使 `h_bitstring = -0.0`，`h_assessed = -0.0`。修复后 `_com_exp` 返回 `E[log2(gap)] = Σ log2(k) * p * q^(k-1)`，对于随机数据 `p≈1/64` 时返回值约 6，二分搜索正确得到 `p≈1/64`，熵估计正常。对比验证：C++ 原版 G(z) 函数同样使用 `pow(1-z, k-1) * z` 加权。

### 9.5 t-Tuple + LRS — `ea/_lrs.py`

**核心难点**：Suffix Array + LCP 的构建。

**实际实现**：**NumPy 向量化的前缀倍增法**（Manber-Myers），未使用 `libdivsufsort`。
每轮把 `(rank[i], rank[i+k])` 二元组打包成**一个 int64 键**，于是一次 `argsort` 就完成排序；
新排名用「排序后相邻键是否变化」的 `cumsum` 一次算出，整轮没有 Python 级循环。

```python
def build_suffix_array(text: np.ndarray, n: int) -> np.ndarray:
    """text[:n] 加上位置 n 处的空后缀（最小）的后缀数组"""
    m = n + 1
    rank = np.empty(m, dtype=np.int64)
    rank[:n] = text[:n]
    rank[n] = -1                       # 空后缀比任何符号都小 → sa[0] == n
    if int(rank[:n].max()) >= n:       # 字母表比样本数还宽时先压实排名
        rank[:n] = np.unique(text[:n], return_inverse=True)[1]

    second = np.empty(m, dtype=np.int64)
    key = np.empty(m, dtype=np.int64)
    k = 1
    while k <= n:
        second.fill(-1)                # second[i] = rank[i + k]，越界为 -1
        if k < m:
            second[:m - k] = rank[k:]
        np.multiply(rank, m + 1, out=key)
        key += second
        key += 1                       # 两个分量都在 [-1, n] → 打包保序

        sa = np.argsort(key)           # 平键拿同一个排名， ties 顺序无关 → 可用非稳定排序
        sorted_key = key[sa]
        rank = np.empty(m, dtype=np.int64)
        rank[sa] = np.concatenate((
            np.zeros(1, dtype=np.int64),
            np.cumsum(sorted_key[1:] != sorted_key[:-1]),
        ))
        if rank[sa[n]] == n:           # 所有后缀已彼此区分 → 顺序即最终顺序
            break
        k <<= 1

    return sa
```

- **复杂度**：每轮 `O(n log n)` 排序 × `O(log n)` 轮，但**循环体全向量化**；4M 位串实测 1.6 s
  （替换掉的纯 Python 版本要 64 s）。随机数据在 6–7 轮内就把所有后缀区分开，提前 break。
- **排序核**：这里必须用非稳定的 introsort——numpy 的 `kind="stable"` 在这批随机键上慢约 6 倍
  （4M 键 1.33 s vs 0.21 s），而**平键会被赋同一个排名，所以轮内顺序不影响任何后续结果**，
  最终 SA 仍然逐元素相同（已按 11 个 refdata 样本逐一确认）。
- **替代方案**（未实现）：ctypes 调用 `libdivsufsort` 可把每轮打包排序换成 O(n) 的 SA-IS，
  但它已经不是关键路径（见 §14.5）。

### Kasai LCP 算法的 Python 实现

`rank` 用一次 fancy-index 散射建好（`rank[sa] = arange(n+1)`）；剩下的 Kasai 主循环是
O(n) 的字符比较，无法向量化，于是把 `text`/`sa`/`rank` 全部转成**普通 Python 列表**再走：
`text` 进来是 uint8 数组，逐个 `text[i]` 取出的开销是列表取元素的数倍，而这个循环每个样本
都要跑一次。4M 位串实测 9.6 s → 5.0 s。

```python
def sa_to_lcp(text: np.ndarray, n: int, sa: np.ndarray) -> np.ndarray:
    """Kasai 等 O(n) LCP 构建"""
    rank = np.empty(n + 1, dtype=np.int64)
    rank[sa] = np.arange(n + 1)

    t, s, r = text[:n].tolist(), sa.tolist(), rank.tolist()

    lcp = [0] * (n + 1)   # 只有 0 号槽保留初值：空后缀在 s[0]，其余槽都会被写到
    lcp[0] = -1
    h = 0
    for i in range(n):
        k = r[i]
        if k > 1:
            j = s[k - 1]
            while (i + h < n) and (j + h < n) and t[i + h] == t[j + h]:
                h += 1
            lcp[k] = h
        if h > 0:
            h -= 1
    return np.array(lcp, dtype=np.int64)
```

### Kaufer 算法的 t-Tuple + LRS

`sa_algs()` 的两个扫描（算 `Q` 数组、算 `S` 数组）是严格串行的栈式算法，完全按 C++ `SAalgs64`
逐行翻译，只换两处载体：**`Q`/`A`/`I`/`S` 用普通 Python 列表**（它们按值被反复读写，长度只有
`v + 3`，而 `v = max(LCP)` 在 4M 位串上才 42），**`S` 的元素用 Python int** 替掉 `uint128_t`（组合数
`(n-i+1)(n-i)/2` 在百万级样本上会超过 int64）。所以这两个循环不可能向量化，成本就是
「每个样本一次 Python 迭代」；其余部分（`u` 的确定、两个 `Pmax` 扫描、置信界反推熵）都是 O(v)。

入口这一段有讲究，因为参考实现读 LCP 时整体错开了一格：

```python
def sa_algs(text: np.ndarray, n: int, k: int, verbose: int = 0, label: str = ""):
    """同时计算 t-Tuple 和 LRS 估计"""
    sa = build_suffix_array(text, n)
    L = sa_to_lcp(text, n, sa).tolist()

    # 参考实现的第 i 项读的是 sa_to_lcp 的 i+1 槽，末尾再补一个 0 代表越界槽。
    # 原地 del + append 比切片重接少一次 n+1 元素拷贝；正因为补的是 0 而真实项
    # 全 >= 0，v 才能直接对整表取 max，不必限定在前 n 项里。
    del L[0]
    L.append(0)
    v = max(L)          # 最长重复子串

    Q = [1] * (v + 1)
    A = [0] * (v + 2)
    I = [0] * (v + 3)
    # ……两个 O(n) 扫描 + O(v) 后处理，与 C++ 逐行同构，见 ea/_lrs.py
```

4M 位串上整函数实测 11 s（冷机：其中 SA 1.4 s、LCP 4.0 s，剩下约 5.7 s 就是这两个扫描）。
改这段代码时用 `est_test_nist_cpp_recode/lrs_bench.py`（`make lrs_bench`）对拍 SA/LCP 的
中间量指纹，不只看熵值。

### 9.6 MultiMCW — `ea/multi_mcw.py`

```python
def multi_mcw_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """Section 6.3.7: 多窗口中频次预测"""
    NUM_WINS = 4
    W = [63, 255, 1023, 4095]

    if length < W[-1] + 1:
        return -1.0

    scoreboard = [0] * NUM_WINS
    win_cnts = [np.zeros(alph_size, dtype=np.int64) for _ in range(NUM_WINS)]
    win_poses = [np.zeros(alph_size, dtype=np.int64) for _ in range(NUM_WINS)]
    max_cnts = [0] * NUM_WINS
    frequent = [0] * NUM_WINS

    # 初始化窗口
    for i in range(W[-1]):
        for j in range(NUM_WINS):
            if i < W[j]:
                win_cnts[j][data[i]] += 1
                if win_cnts[j][data[i]] >= max_cnts[j]:
                    max_cnts[j] = win_cnts[j][data[i]]
                    frequent[j] = data[i]
                win_poses[j][data[i]] = i

    # 预测循环
    winner = 0
    C = 0
    run_len = 0
    max_run_len = 0
    for i in range(W[0], length):
        if frequent[winner] == data[i]:
            C += 1
            run_len += 1
            max_run_len = max(max_run_len, run_len)
        else:
            run_len = 0

        # 更新计分板
        for j in range(NUM_WINS):
            if i >= W[j] and frequent[j] == data[i]:
                scoreboard[j] += 1
                if scoreboard[j] >= scoreboard[winner]:
                    winner = j

        # 滑动窗口
        for j in range(NUM_WINS):
            if i >= W[j]:
                out_sym = data[i - W[j]]
                in_sym = data[i]
                win_cnts[j][out_sym] -= 1
                win_cnts[j][in_sym] += 1
                win_poses[j][in_sym] = i  # 平局裁决要用：见下方说明
                if out_sym != frequent[j] and max_cnts[j] <= win_cnts[j][in_sym]:
                    max_cnts[j] = win_cnts[j][in_sym]
                    frequent[j] = in_sym
                elif out_sym == frequent[j]:
                    max_cnts[j] -= 1
                    # 搜索新的 frequent
                    idx = np.argmax(win_cnts[j])
                    if win_cnts[j][idx] > max_cnts[j]:
                        max_cnts[j] = win_cnts[j][idx]
                        frequent[j] = idx

    N = length - W[0]
    return prediction_estimate(C, N, max_run_len, alph_size, "MultiMCW", verbose, label)
```

> **`win_poses` 不是死代码**（本文档早先这么写过，是错的）：它在 `ea/multi_mcw.py:74`
> （CPython 版）与 `:164`（numba kernel 版）被读出来当 `poses`，用于 incumbent 失去领先时
> 那次字母表 rescan 的**平局裁决**——比较口径是 `max_pos <= win_poses[k]`，即计数相同时
> 取最近出现位置更靠后的那个符号。删掉它会改变 `frequent[j]` 的取值，进而改变
> `correct_count`，属于会动输出数字的改动。

### 9.7 Lag — `ea/lag_test.py`

> 本节早先贴的是一份「Ring Buffer 方案」代码（`LagBuffer()` + `cur_rb.buf[ci & LAGMASK]` +
> 手工推进 `start`/`end`）。**那不是现在的实现**——`LagBuffer` 类不存在（见 §3.8）。
> 下面按 `ea/lag_test.py` 的实际代码重贴。

CPython 侧用「每符号一条升序出现位置列表 + `bisect_left` 裁剪」替掉参考实现的环形缓冲：

```python
scoreboard = [0] * D_LAG
occurs = [[] for _ in range(alph_size)]
occurs[syms[0]].append(0)          # 第一个符号没有猜测可言

winner = correct_count = cur_run = max_run = high_score = 0

for i in range(1, length):
    cur_sym = syms[i]
    seen = occurs[cur_sym]

    # 先验预测：winner 是更早的样本上选出的 lag，不会回越过样本开头
    lag_idx = i - winner - 1
    if lag_idx >= 0 and syms[lag_idx] == cur_sym:
        correct_count += 1
        cur_run += 1
        if cur_run > max_run:
            max_run = cur_run
    else:
        cur_run = 0

    # 更新计分板：该符号仍在最近 D_LAG 个样本内的每次出现，都给它所隐含的 lag 记一分。
    # 位置按最旧在前的顺序存、窗口每样本滑动一格，所以游走会停下的项全在前面。
    if seen:
        cutoff = i - D_LAG if i >= D_LAG else 0
        stale = bisect_left(seen, cutoff)
        if stale:
            del seen[:stale]
        for pos in reversed(seen):        # 最新出现优先 = lag 升序
            lag = i - pos - 1
            score = scoreboard[lag] + 1
            scoreboard[lag] = score
            if score >= high_score:
                winner = lag
                high_score = score

    seen.append(i)

return correct_count, max_run
```

- **为什么不需要环**：模块 docstring 给了理由——游走最多停在最近 `D_LAG` 个样本内，
  环里不可能存在「窗口过滤会保留、而环已丢弃」的项，所以两种载体等价。
- **`D_LAG` 从 `_config` 导入**（`lag_test.py:9`），不是硬编码；`LAGMASK` 在 CPython 侧根本用不到。
- **numba kernel 侧**（`_lag_kernel`，`lag_test.py:78` 起）才逐字照搬参考实现的 `lagBuf`：
  一个 `(alph_size, D_LAG)` 的 int64 numpy 环。两侧数据结构不同、原始计数必须相同，
  由 `jit_crosscheck.py` 对拍（这一行同时是「数据结构对译」的验证点）。
- 外层 `lag_test()` 拿 `(correct_count, max_run)` 去调
  `prediction_estimate(correct_count, length - 1, max_run, alph_size, "Lag", ...)`。
- 符号流以 `bytes` 访问（见 §17「已实现的性能优化」末条），不是逐个 numpy 标量索引。

### 9.8 MultiMMC — `ea/multi_mmc.py`

**二进制优化版本**：
```python
def binary_multi_mmc_prediction_estimate(
    data: np.ndarray, length: int, verbose: int = 0, label: str = ""
) -> float:
    D = D_MMC  # 16
    scoreboard = [0] * D
    # binaryDict[d]: 长度为 d+1 的前缀模式 → [count_0, count_1]
    # 索引：模式 << 1 + 0/1 = 模式*2 + 0/1
    binary_dict = [np.zeros(1 << (d + 2), dtype=np.int64) for d in range(D)]
    dict_elems = [0] * D
    winner = 0

    # 初始化
    cur_pattern = 0
    for d in range(D):
        cur_pattern |= (int(data[d]) & 1) << d
        binary_dict[d][(cur_pattern << 1) | (int(data[d + 1]) & 1)] = 1
        dict_elems[d] = 1

    correct_count = 0
    cur_run = 0
    max_run = 0

    for i in range(2, length):
        cur_winner = winner
        cur_pattern = 0
        found_x = False

        for d in range(D):
            if d > i - 2:
                break
            cur_pattern |= (int(data[i - d - 1]) & 1) << d
            cur_pattern &= (1 << (d + 1)) - 1  # 限制为 d+1 位

            entry = binary_dict[d]  # ⚠ 必须移到 if 外：found_x 变 False 后另个 d 仍使用正确字典

            if d == 0 or found_x:
                idx = cur_pattern << 1
                c0, c1 = entry[idx], entry[idx + 1]
                if c0 > c1:
                    cur_prediction, cur_count = 0, c0
                else:
                    cur_prediction, cur_count = 1, c1

                found_x = cur_count > 0

            if found_x:
                if cur_prediction == (int(data[i]) & 1):
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        correct_count += 1
                        cur_run += 1
                        max_run = max(max_run, cur_run)
                elif d == cur_winner:
                    cur_run = 0

                # 更新字典
                entry[cur_pattern << 1 | (int(data[i]) & 1)] += 1

            elif dict_elems[d] < MAX_ENTRIES:
                entry[cur_pattern << 1 | (int(data[i]) & 1)] = 1
                dict_elems[d] += 1

    return prediction_estimate(correct_count, length - 2, max_run, 2, "MultiMMC", verbose, label)
```

### 9.9 LZ78Y — `ea/lz78y.py`

类似 MultiMMC 的结构，使用 16 个 context-length 字典，每个字典键为前缀模式，值为 `[count_0, count_1]`。

与 MultiMMC 共享同一 bug 模式（已在 2026-05-20 修复）：

```python
# ❌ 错误：found_x 变 False 后 entry 未更新，cur_pattern 增长导致索引越界
if d == 0 or found_x:
    entry = binary_dict[d]  # 只在这里赋值

# ✅ 修复：将 entry = binary_dict[d] 移到 if 外面，保证每个 d 使用正确字典
entry = binary_dict[d]
if d == 0 or found_x:
    ...
```

**关键修复**：当 `found_x` 变为 `False` 时，`if d == 0 or found_x:` 分支不再执行，导致 `entry` 仍指向 `binary_dict[previous_d]`（如 size=8），但 `cur_pattern` 随 `d` 增长已包含更多位，计算出的索引超出旧字典范围。将 `entry = binary_dict[d]` 提到 `if` 外后，每个 `d` 循环始终使用大小匹配的字典。

### 9.10 `BINARYDICTLOC` 宏的 Python 替代

```python
def binary_dict_loc(d: int, pattern: int, base_dicts: list[np.ndarray]) -> np.ndarray:
    """
    返回指向 binaryDict[d-1][pattern的低d位 * 2] 的视图
    C++ 原版: BINARYDICTLOC(d, b) = binaryDict[(d)-1] + (((b) & ((1U << (d)) - 1))<<1)
    """
    idx = (pattern & ((1 << d) - 1)) << 1
    return base_dicts[d - 1][idx:idx + 2]
```

---

## 10. Prediction Estimate 框架

统一入口函数，被 MultiMCW、Lag、MultiMMC、LZ78Y 调用。

```python
def prediction_estimate(
    C: int, N: int, max_run_len: int, k: int,
    test_name: str = "", verbose: int = 0, label: str = ""
) -> float:
    """
    预测估计的统一框架。

    参数：
        C: 正确预测次数
        N: 总预测次数
        max_run_len: 最长连续正确长度
        k: 字母表大小
    返回：
        min-entropy = -log2(max(p_global', p_local))
    """
    cur_max = 1.0 / k
    p_global = C / N

    if p_global > 0:
        p_global_prime = min(1.0, p_global + ZALPHA * math.sqrt(
            p_global * (1.0 - p_global) / (N - 1.0)))
    else:
        p_global_prime = 1.0 - 0.01 ** (1.0 / N)

    cur_max = max(cur_max, p_global_prime)

    r = max_run_len + 1
    if cur_max < 1.0 and _prediction_estimate_function(cur_max, r, N) > math.log(0.99):
        p_local = calc_p_local(max_run_len, N, cur_max)
        cur_max = max(cur_max, p_local)

    return -math.log2(cur_max)
```

**`calc_p_local`** 的二分搜索使用与 C++ 完全相同的 `rel_epsilon_equal` 终止条件。

---

## 11. Restart 测试模块

### 11.1 模拟计数

```python
def simulate_count(k_effective: int, p: float, seed: list[int]) -> int:
    """
    模拟一行（1000个独立同分布样本），返回最频繁符号的出现次数。
    分布：floor(1/p) 个符号各概率 p，余下的给一个残差符号。
    """
    rng = Xoshiro256StarStar(np.array(seed, dtype=np.uint64))
    counts = np.zeros(k_effective, dtype=np.uint16)
    for _ in range(1000):
        idx = int(math.floor(rng.random_unit() / p))
        if idx >= k_effective:
            idx = k_effective - 1
        counts[idx] += 1
    return int(np.max(counts))


def simulate_batch(
    num_rounds: int, k_effective: int, p: float, base_seed: list[int]
) -> list[int]:
    """批量运行模拟轮次，每轮使用不同 seed（避免 RNG 状态冲突）。"""
    results = []
    for i in range(num_rounds):
        seed = [(s + i * 7 + 13) & 0xFFFFFFFFFFFFFFFF for s in base_seed]
        results.append(simulate_count(k_effective, p, seed))
    return results
```

### 11.2 模拟边界

```python
def simulate_bound(
    alpha: float, k: int, H_I: float,
    simulation_rounds: int = DEFAULT_SIM_ROUNDS,
    num_workers: int | None = None,
) -> int:
    """Monte Carlo 模拟求 X_cutoff（使用 ProcessPoolExecutor 并行）"""
    p = 2.0 ** (-H_I)
    k_effective = math.ceil(1.0 / p)
    assert 1 < k_effective <= k <= 256

    if num_workers is None:
        num_workers = os.cpu_count() or 1

    base_seed = [0x1234567890ABCDEF, 0xFEDCBA0987654321,
                 0x1111111111111111, 0x2222222222222222]
    batch_size = simulation_rounds // num_workers
    if batch_size == 0:
        batch_size = 1

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        futures = []
        for _ in range(num_workers):
            futures.append(ex.submit(simulate_batch, batch_size, k_effective, p, base_seed))
        results = []
        for f in futures:
            results.extend(f.result())

    results.sort()
    return_index = int(math.floor((1.0 - alpha) * simulation_rounds)) - 1
    if return_index < 0:
        return_index = 0
    if return_index >= len(results):
        return_index = len(results) - 1
    return results[return_index]
```

### 11.3 主流程

```python
def restart_test(
    file_path: str, H_I: float, iid: bool = False,
    verbose: int = 1, simulation_rounds: int = DEFAULT_SIM_ROUNDS
) -> float:
    """完整的 Restart 测试"""
    data = DataT()
    if not read_file(file_path, data):
        raise RuntimeError("Failed to read file")

    assert data.len == MIN_SIZE, f"Need {MIN_SIZE} samples"
    assert H_I <= data.word_size
    assert data.alph_size > 1

    r, c = 1000, 1000
    rdata = data.symbols

    # 转置为列数据
    cdata = np.zeros(data.len, dtype=np.uint8)
    for j in range(c):
        for i in range(r):
            cdata[j * r + i] = rdata[i * c + j]  # 实际实现 (r==c==1000 时结果相同)

    # Sanity Check
    alpha = 1 - math.exp(math.log(0.99) / (r + c))
    X_cutoff = simulate_bound(alpha, data.alph_size, H_I, simulation_rounds)

    # 找最大行计数 / 列计数
    X_r = _max_count_in_rows(rdata, r, c, data.alph_size)
    X_c = _max_count_in_rows(cdata, c, r, data.alph_size)  # 转置后行列互换
    X_max = max(X_r, X_c)

    if X_max > X_cutoff:
        raise RuntimeError("Restart Sanity Check Failed")

    # Validation Test — 用 MCV 估计 H_r, H_c
    H_r = min(data.word_size, most_common_value(rdata, data.len, data.alph_size, ...))
    H_c = min(data.word_size, most_common_value(cdata, data.len, data.alph_size, ...))

    if iid:
        # 完整 IID 检测 (χ² + LRS + 置换)
        ...
    else:
        # 完整 non-IID 检测 (若 alph_size==2 则全部检出)
        ...

    if min(H_r, H_c) < H_I / 2.0:
        raise RuntimeError("Validation Test Failed")

    return min(H_r, H_c, H_I)
```

---

## 12. Conditioning 模块

### 定位

Conditioning 的 `Output_Entropy` 计算需要任意精度算术（MPFR），Python 使用 `mpmath` 实现。

```python
import mpmath as mp

def compute_output_entropy(
    h_in: float, n_in: int, n_out: int, nw: int,
    precision_bits: int = 128
) -> tuple[float, float, float, float]:
    """
    Section 3.1.5.1.2 Output_Entropy

    返回:
        (h_out, nout_epsilon_exp, hin_epsilon_exp, nw_epsilon_exp)
    """
    mp.mp.dps = precision_bits // 4  # 约 precision/4 位十进制

    n = min(n_out, nw)

    # Step 1: p_high = 2^(-h_in), p_low = (1-p_high)/(2^n_in - 1)
    p_high = mp.power(2, -mp.mpf(h_in))
    if p_high <= 0 or p_high >= 1:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    p_low = (1 - p_high) / (mp.power(2, n_in) - 1)
    if p_low <= 0 or p_low >= 1:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    # Step 3: Psi = 2^(n_in-n) * p_low + p_high
    power_term = mp.power(2, n_in - n)
    psi = power_term * p_low + p_high
    psi = min(psi, mp.mpf(1))

    # Step 4: Omega = (2^(n_in-n) + sqrt(log(2) * 2^(n_in-n) * 2n)) * p_low
    omega = (power_term + mp.sqrt(mp.log(2) * power_term * 2 * n)) * p_low
    omega = min(omega, mp.mpf(1))

    # Step 6: h_out = -log2(max(omega, psi))
    h_out = -mp.log(max(omega, psi), 2)

    if h_out >= n_out or h_out >= h_in:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    # 计算 epsilon 值
    nout_eps = _calc_epsilon(h_out, n_out)
    hin_eps = _calc_epsilon(h_out, h_in)
    nw_eps = _calc_epsilon(h_out, nw)

    return float(h_out), float(nout_eps), float(hin_eps), float(nw_eps)


def _calc_epsilon(h_out: mp.mpf, bound: float) -> float:
    """epsilon = -log2(1 - h_out/bound)"""
    return float(-mp.log(1 - h_out / mp.mpf(bound), 2))
```

**关键**：C++ 中 MPFR 使用 `MPFR_RNDZ`（toward zero）和 `MPFR_RNDU`（+∞），Python 的 `mpmath` 默认 round-to-nearest。要复现保守估计，需要手动控制 rounding direction：

```python
# 近似 RNDU (向+∞)
with mp.extraprec(20):  # 额外精度 + 最终截断，近似 RNDU
    ...
```

---

## 13. 主入口与 CLI

### 13.1 CLI 结构

使用 Python `argparse`，每个 CLI 模块独立脚本：

```python
# cli/ea_iid.py
def main():
    parser = argparse.ArgumentParser(description="ea_iid — IID Entropy Assessment")
    parser.add_argument("file", help="Binary data file")
    parser.add_argument("bits_per_symbol", nargs="?", type=int, default=0)
    parser.add_argument("-i", "--initial", action="store_true", dest="initial",
                        help="Initial entropy estimate (default)")
    parser.add_argument("-c", "--conditioned", action="store_false", dest="initial",
                        help="Conditioned dataset estimate")
    parser.add_argument("-a", "--all", action="store_true", dest="all_bits",
                        help="Use all bits for H_bitstring (default)")
    parser.add_argument("-t", "--truncate", action="store_false", dest="all_bits",
                        help="Truncate H_bitstring to first million bits")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    parser.add_argument("-j", "--workers", type=int, default=None, metavar="N")
    parser.set_defaults(initial=True, all_bits=True)   # 必须在 parse_args() 之前
    args = parser.parse_args()
    ...
```

**坑**：`-i/-c`（以及 `-a/-t`）共用一个 `dest`，argparse 在填默认值时取**第一个** action 的
`default`，即 `store_true` 的 `False`；而 `set_defaults()` 会同时改写已注册 action 的 `default`，
所以它必须在 `parse_args()` **之前**调用才有效。写反了的后果是：不带 `-a/-t` 跑 `ea_iid` 时
`all_bits=False`，`H_bitstring` 被静默截断到前 100 万位（同时 test case 被标成 "Conditioned"）。

### 13.2 JSON 输出

**注意**：实际实现中未使用 `NumpyEncoder` 类。CLI 模块直接调用 `json.dump(run.to_dict(), f, indent=2)`，因为 `to_dict()` 方法已手动转换所有 numpy 类型为 Python 原生类型。

### 13.3 入口点

**注意**：`pyproject.toml` 已从项目中移除。CLI 模块通过 `sys.path.insert()` 自举运行。
集成测试入口由 `est_test/est_test_nist_c++_recode.py` 提供。

原 `pyproject.toml` 脚本顺序（已废弃）：
```toml
[project.scripts]
ea_restart = "cli.ea_restart:main"
ea_iid = "cli.ea_iid:main"
ea_non_iid = "cli.ea_non_iid:main"
ea_conditioning = "cli.ea_conditioning:main"
ea_transpose = "cli.ea_transpose:main"
```

---

## 14. 性能加速策略

### 14.1 Numba JIT（可选依赖，已实现）

四个逐样本在线预测器（`multi_mcw` / `lag_test` / `multi_mmc` / `lz78y`）各有一份**纯 Python 循环**
与一份 **numba kernel**（两者都只返 `correct_count` / `max_run`），`ea/_jit.py` 负责在两者之间选：

| 机制 | 取值 | 为什么 |
|------|------|--------|
| 延迟导入 | 首次 `use_jit()` 才 `import numba` | 载入 numba 约 0.4 s，万级样本上整个估计只要几毫秒 |
| `JIT_MIN_SAMPLES` | 100 000 符号 | 盈亏点：Python MultiMMC 约 9 µs/符号 → 10 万 ≈ 1 s，对得上 0.5 s 载入 / 1.6 s 冷编译 |
| `cache=True` | kernel 机器码落 `__pycache__` | 新进程首次调用 ≈ 0.5 s（基本只是 import），每个 worker 只付一次 |
| `EA_DISABLE_JIT=1` | 强制走 Python 循环 | 与 JIT 前的构建树做同轮 A/B |
| `frozen()` | 打包可执行文件里整体禁用 | 冻结包未必带上 llvmlite，也未必有可写目录放缓存 |

`Kernel` 代理在首次调用时才编译；numba 缺失、导入失败或编译失败时**照旧跑同一函数体的
CPython 解释版**，所以三条路（无 numba / 有 numba 但未达门槛 / 有 numba 且达门槛）给出的数字逐位相同。

kernel 侧顺手换了数据结构：二进制 MultiMMC / LZ78Y 把「一张表一个长度」的 list-of-lists
平铺进一个 `int64` 大数组（偏移分别为 `2^(d+2)-4` 与 `2^(j+2)-8`），Lag 回到参考实现的 128 槽
环形缓冲（Python 侧保留「升序位置列表 + 二分裁剪」那份等价写法），MultiMCW 的四张窗口表合成
两个二维数组，`W` 以数组形参传入（global Python list 没有 numba 类型）。

等价性由 `est_test_nist_cpp_recode/jit_crosscheck.py` 把关：11 个 refdata 样本 × 两个视图 ×
4 个预测器共 56 项，要求两侧原始计数逐位相同、且 `Kernel.compiled` 非空（静默退回 Python
侧会让「两边相同」变成同义反复）。计数循环实测 45–250× 加速，端到端效果见 §14.5。

当初计划里的 `collision_test` / `markov_test` / `permutation.run_tests` / `compression_test`
未做 JIT：Markov 是 numpy 向量化、压缩检验走 bz2（C 级），IID 侧单轮 19 项统计里 bz2 占 56–82%，
瓶颈不在 Python 循环上。

### 14.2 NumPy 向量化

**已应用**：
- MCV 的 `np.bincount`
- Markov 的滑动窗口差 `data[1:]` / `data[:-1]`
- 符号映射

### 14.3 后缀数组：NumPy 向量化前缀倍增

**实际状态**：每轮把 `(rank[i], rank[i+k])` 打包成一个 int64 键后交给一次 `np.argsort`，
新排名由相邻键差异的 `cumsum` 得出，循环体没有 Python 级循环（详见 §9.5）。未使用 `libdivsufsort`。
在 1M 字节样本上，位串视图（4M 符号）的 t-Tuple+LRS 从 70 s 降到 11–16 s，
其中后缀数组 64 s → 1.4–2.0 s、Kasai LCP 9.6 s → 4.0–6.3 s、Kaufer 扫描 ≈ 5.5 s（纯 Python，仍是 O(n) 逐样本）。
两个区间是同机冷/热态之差（见 §14.5 末尾的说明），比值稳定。
剩下的 LCP 与 Kaufer 扫描都是“每个样本一次 Python 迭代”的量级，向量化需要额外的排名阶梯
（可用已保存的每轮 rank 数组以 O(n log n) 批量重建 LCP），目前不值得那份复杂度。
§14.1 的 JIT 落地后，Kaufer 扫描（≈ 11.8 s）成了新的最贵单 job，而它仍是一份额外的 Python 循环
⇒ 下一步最有希望的正是把它也交给 numba（向量化依旧不合适，见 §14.5 末尾）。

### 14.4 并行化

| 模块 | 文档计划 | 实际实现 |
|------|---------|---------|
| 置换检验 (10000轮) | `ProcessPoolExecutor` | **轮次并行** ✓（默认每个物理核 1 个进程，`-j/--workers` 可覆盖；shuffle 按轮独立播种，计数与判定仍在主进程按轮序完成）|
| 非 IID 各估计 | 未计划 | **估计器并行** ✓（默认每个物理核 1 个进程，`-j/--workers` 可覆盖；估计器打印的明细行由 worker 带回、主进程按参考顺序重放，所以 `-j 1` 与并行输出的唯一差异是 timestamp/commandline）|
| Restart 模拟 (5M轮) | `ProcessPoolExecutor` + numpy 向量化 | **`ProcessPoolExecutor` 并行** ✓ |
| 符号映射 (大文件) | 向量化 numpy | 向量化 numpy ✓ |

三处并行共用 `ea/_parallel.py`（`auto_workers()` / `open_pool()` / `capture()` / `ParallelJobs`）：
启动不了 worker 的入口（冻结可执行文件、无多余进程名额）会打印警告退回串行；
`auto_workers()` 在冻结构建下直接返回 1；worker 自己不得再开池（`inside_worker()`）。

### 14.5 实际性能参考

下表为 i7-11800H 上**单进程**、1M 字节样本 `truerand_4bit.bin`（位串视图 4M 符号 + 符号视图 1M 符号）
的逐 job 计时（`est_test_nist_cpp_recode/job_bench.py`，kernel 已编译），两个数字依次对应位串与符号。
两列来自**同一轮**：先冷机跑 `EA_DISABLE_JIT=1`，停 20 s 再跑开 JIT 的那一遍——这个顺序只会低估
加速比（第二遍在热态），不会虚报；而不受 JIT 影响的行（t-Tuple+LRS、Collision、Markov、
Compression）在两列里几乎重合，说明这一轮本身可比。

| 模块 | 实现方式 | `EA_DISABLE_JIT=1` | 开 JIT |
|------|---------|-------------------|--------|
| 文件读取+映射 | numpy | 毫秒级 | — |
| MCV | numpy bincount | 毫秒级 | — |
| Collision | 纯 Python 循环 | 0.83 s（不跑符号视图）| 0.82 s |
| Markov | numpy 向量化 | 0.02 s | 0.02 s |
| Compression | 纯 Python + Kahan | 0.29 s | 0.29 s |
| MultiMCW | **njit** + 二维计数表 | 14.75 s + 2.80 s | **0.61 s + 0.03 s** |
| Lag | **njit** + 128 槽环形缓冲 | 32.82 s + 1.56 s | **0.32 s + 0.02 s** |
| MultiMMC | 二进制定制版 **njit**；通用字母表仍是纯 Python + dict | 34.00 s + 8.31 s | **0.47 s** + 8.38 s |
| LZ78Y | 二进制定制版 **njit**；通用字母表仍是纯 Python + dict | 26.63 s + 5.37 s | **0.26 s** + 5.31 s |
| t-Tuple+LRS | **numpy 向量化前缀倍增** + 纯 Python Kaufer 扫描（§9.5）| 11.92 s + 2.02 s | 11.80 s + 2.02 s |
| 置换检验 (10000轮) | 轮次并行 | 1M 字节样本全量约 21 min（同机串行外推约 69 min）| 同左 |
| Restart (5M轮) | ProcessPoolExecutor 并行 | 较快（CPU 核数线性加速）| 同左 |
| Conditioning | mpmath | 毫秒级 | — |

Collision / Markov / Compression 按参考实现「仅用于位串」，多比特样本上不会跑符号视图，故只有一个数字。

末行汇总：单估计器相加 141.33 s → **30.33 s**，最长 job 34.00 s（MultiMMC/位串）→ **11.80 s**
（t-Tuple+LRS/位串）。四个在线预测器两个视图合计 126.2 s → 15.4 s，其中位串侧 108.2 s → **1.66 s**（65×）；
剩下的 13.7 s 全在通用字母表的 MultiMMC / LZ78Y 上（还是 dict + `PostfixDictionary`，没 JIT）。

IID 那侧与这里相反：单轮 19 项统计里 **bz2 压缩检验占 56–82%**（它是 C 级实现，0.36 s/轮），
其次是纯 Python 的碰撞检验（非二进制样本上 32%），其余 16 项向量化统计合计不到 10%；
那一侧的墙钟由 10000 轮置换乘以轮数决定，至今仍是分钟级（见上表）。

JIT 前后的同轮端到端 A/B（`EA_DISABLE_JIT=1` 对照，只改这个开关，`H_assessed` 逐字相同）：

| | `-j 1` | `-j 8` |
|---|--------|--------|
| 有 JIT | 30.4 s | 16.9 s |
| `EA_DISABLE_JIT=1` | 142.6 s | 61.3 s |

上表的 `-j 1` 两列与逐 job 表的 SUM（30.33 / 141.33 s）互验：单进程跑完全部估计器的量
几乎就是端到端本身，父进程开销在 0.5 s 以内。

剩下的钱在 `sa_algs` 的 Kaufer 扫描（位串侧 11.8 s，仍未交给 numba）与通用字母表的
MultiMMC / LZ78Y（8.4 / 5.3 s）上——三者各自都不超过 12 s，所以墙钟已经进到 20 s 量级。

`-j` 从 1 扫到 12（同机、同一文件、只改进程数，`H_assessed` 逐字相同）：

| `-j` | 1 | 2 | 3 | 4 | 6 | 8 | 12 |
|------|---|---|---|---|---|---|----|
| 墙钟 s | 34.2 | 21.6 | 17.4 | 16.2 | 16.0 | 16.8 | 18.0 |

4 进程往上就是 16–18 s 的平台，默认值（每个物理核 1 个 = 8）正落在平台里，**没有再调 `-j` 的空
间**；瓶颈仍是最贵的单个估计器（现在是位串视图的 t-Tuple+LRS 11.8 s），而不是进程数。与 JIT 前
不同的一点：过 6 进程后墙钟开始回升，因为每个 worker 都要付一次 numba 导入 + 缓存装载。
实测墙钟 ≈ 1.3 × 最长 job（JIT 前是 1.5 ×）。

另一端的代价也量过：尺寸门槛让样本不足 10 万时连 numba 都不导入，A/B 下是纯噪声
（`rand8_short` 2.76 / 1.42 s ↔ 2.84 / 1.50 s，`rand1_short` 0.48 / 0.74 s ↔ 0.46 / 0.77 s，
依次为 `-j 1` / `-j 8`，差都落在 ±6%）。开池本身在小样本上仍然多花约 0.3 s，但 8 万个位串
样本就重新划算。为这点绝对量加一个尺寸阈值只会是个拍脑袋的魔法数，故不加阈值；需要时用
`-j 1` 即可。

> 本机是笔记本，持续负载下会降频：紧接着一轮 10 次端到端之后再测同一套 job，
> 全部整体 ×1.3（sum 150 → 176 s，MultiMMC 35.9 → 49.0 s），排序和比值不变。
> 因此本文的耗时一律给区间，比较只认同一次冷机测量内的相对值。JIT 之后同一命令的
> 重复测量仍能差到 20%（`-j 8`：20.5 / 16.8 / 16.9 s），所以上面凡是要用来下结论的数字
> 都做了同轮 A/B，而不是拿不同时间的测量互比。

---

## 15. 测试与验证

### 15.1 集成测试入口

`tests/` 目录已从 `est_core_nist_cpp_recode/` 移除。集成测试通过 `est_test/est_test_nist_c++_recode.py` 执行：

```powershell
python est_test\est_test_nist_c++_recode.py data.bin --iid --non-iid --restart --h-i 0.9
```

### 15.2 自测方案（参考）

与 C++ 版本的自测方式一致：使用 `bin/` 中的 11 个测试文件，与 `selftest/refdata/` 中的参考输出对比。

```python
# tests/test_selftest.py
def test_against_reference():
    test_files = list(Path("bin").glob("*.bin"))
    for f in test_files:
        # Run Python version
        result = run_non_iid(str(f))

        # Load reference data
        ref_file = Path(f"selftest/refdata/{f.stem}.res")
        ref_values = parse_reference_file(ref_file)

        # Compare each numeric value
        for key, ref_val in ref_values.items():
            py_val = extract_value(result, key)
            delta = abs(py_val - ref_val)
            max_val = max(abs(py_val), abs(ref_val))
            rel_delta = delta / max_val if max_val > 0 else 0
            assert delta < 1e-6 or rel_delta < 1e-6, \
                f"{f.name}: {key} delta={max(delta, rel_delta)}"
```

### 15.3 逐模块测试（参考）

每个模块的测试策略：

| 模块 | 测试方法 | 测试数据 |
|------|---------|---------|
| `_rng.py` | 与参考实现对比前 1000 个随机数 | 确定性种子 |
| `_io.py` | 已知文件 + 已知 word_size | `rand1_short.bin` 等 |
| `chi_square.py` | scipy 对照 + C++ 输出对照 | `normal.bin` |
| `permutation.py` | C++ 输出对照 | `normal.bin` |
| `mcv.py` | C++ 输出对照 | 所有 bin 文件 |
| `collision.py` | C++ 输出对照 | 所有 bin 文件 |
| `markov.py` | C++ 输出对照 | 所有 bin 文件 |
| `compression.py` | C++ 输出对照 | 所有 bin 文件 |
| `_lrs.py` | C++ 输出对照 | 所有 bin 文件 |
| `multi_mcw.py` | C++ 输出对照 | 所有 bin 文件 |
| `lag_test.py` | C++ 输出对照 | 所有 bin 文件 |
| `multi_mmc.py` | C++ 输出对照 | 所有 bin 文件 |
| `lz78y.py` | C++ 输出对照 | 所有 bin 文件 |
| `restart.py` | C++ 输出对照 | 构造 1M 样本测试文件 |
| `conditioning.py` | 已知参数对照 | 无文件 |

### 15.4 精度验收标准

| 层级 | 最大允许偏差 | 说明 |
|------|------------|------|
| 严格 | 1e-10 | 用于 MCV、Collision、Markov 等纯 double 运算 |
| 正常 | 1e-6 | 用于涉及 pow/log 的 t-Tuple、LRS、Prediction |
| 宽松 | 1e-2 | 置换检验（因随机排列结果天然有差异） |

**注意**：由于 C++ 的 `long double`（80-bit extended）与 Python 的 `double`（64-bit IEEE 754）精度差异，t-Tuple、LRS 和 Prediction Estimate 的结果在最后几位（约 1e-12 级别）可能有微小差异。如果自测要求达到 C++ 一样的 1e-10 内部一致性，上述精度敏感部分可能需要使用 `mpmath` 替代。

### 15.5 refdata 逐行文本比对

保真度检查已经不再需要自定义解析器：`ea_non_iid.py <file> -vv` 打印的每一行 `… Estimate: …`
与 C++ 的行数、字段名、出现顺序完全一致，于是比对退化成逐行比较，已固化为
`est_test_nist_cpp_recode/refdata_diff.py`（默认 3 个短样本秒级完成，`--all` 跑满 11 个，
退出码 0/1，也可 `make refdata_diff`）。

11 个 refdata 样本上的结果：行数 100% 相同（binary 样本只有一份视图、全用 `Literal` 前缀，共 63 行；
多比特样本为 `Bitstring` 63 行 + `Literal` 41 行 = 104 行），字段名与行序零漂移，残余数值差异只有三类：

- `%.22Lg` 行（t-Tuple / LRS 的 `p-hat`、`p_u`）：C++ 打印的是 80-bit `long double`，Python 只有
  `double`，第 17 位以后必然不同；
- 经 `log2` / `sqrt` 派生的 `p`、`min entropy`：最多 1–2 ULP（相对 1e-15 量级），来自 libm 差异
  ——refdata 本身是在 Linux/glibc 下生成的；
- `calc_p_local` 二分搜索的收敛点：11 个样本共 476 行预测器输出（其中 68 行 `min entropy`），
  只有 ringOsc-nist 的 MultiMCW 一行越过了 1e-9——`P_local` 本身相差不到 1e-9（在容差内），
  而 `-log2` 按 1/|ln p| 再放大相对误差（p≈0.818 时约 5 倍），派生的 `min entropy` 就到了
  1.1e-9。仍远在 §15.4 「预测器 1e-6」档内，但默认容差取 1e-9 时这一行会报 value mismatch，
  验收预测器派生值时用 `--tol 1e-6`。

前提是这几个模块的 verbose 文本逐字照抄参考实现：`mcv.py`（verbose 2 为 `MCV Estimate: mode / p-hat / p_u`，
verbose 3 为 `Most Common Value Estimate: Mode count / p-hat / p_u / min entropy`——两个层级的段名不同）、
`collision.py`（`v / Sum t_i / X-bar / sigma-hat / X-bar' / Found p. / p / min entropy`）、
`markov.py`（`P_0 / P_1 / P_{0,0} … P_{1,1} / p-hat_max / min entropy`，注意 verbose 2 打成 `p_max`、
且整段挤在一行）。`compression.py` 与 `_util.py` 的 prediction 段本来就是逐字对齐的。

唯一保留的文本偏差：碰撞估计里 `v == 0`（只在样本不超过 2 位时发生）时我们打印
`Collision Estimate: No collisions found.` 并返回 -1.0（失败哨兵），而参考实现此处会除以 0 得到 `nan`。

---

## 16. 依赖清单

### 16.1 运行时依赖

| 包 | 版本要求 | 用途 | 替代方案 |
|----|---------|------|---------|
| `numpy` | ≥1.24 | 数组操作、符号映射、`bincount` | 纯 Python（慢 100x） |
| `scipy` | ≥1.10 (可选) | `gammaincc`（χ² p-value） | 内置 `_cephes_igamc` 回退 |
| `mpmath` | ≥1.3 | 任意精度 Conditioning | `decimal.Decimal` |
| `numba` | ≥0.59（可选）| 四个逐样本预测器的热点循环（§14.1）| 纯 Python 双胞胎（自动回退，结果相同，非 IID 串行约慢 4.7×）|

**注意**：`numba` 是**可选**的：缺失时 `ea/_jit.py` 直接跑同一函数体的 Python 版，算出来的数字
逐位不变，只是慢；打包成单文件可执行时（`frozen()`）整体禁用 JIT。它要求 `numpy >=1.22,<2.6`，
与本项目的 `numpy==2.2.6` 兼容，不需要为此降级 numpy。`libdivsufsort` 未集成，后缀数组用 numpy
前缀倍增实现（§14.3）。Restart 测试（`restart.py`）已使用 `ProcessPoolExecutor` 并行化。

### 16.2 可选依赖

| 包 | 用途 |
|----|------|
| `numba` + `llvmlite` | 四个在线预测器的 `@njit(cache=True)` kernel（§14.1）|
| `libdivsufsort` (系统库 + ctypes) | 后缀数组构建 |
| `python-bz2` (stdlib) | 置换测试的压缩测试 |
| `cffi` / `ctypes` (stdlib) | 调用 C 库 |

### 16.3 开发依赖

| 包 | 用途 |
|----|------|
| `pytest` ≈7.0 | 测试框架 |
| `pytest-benchmark` | 性能回归测试 |
| `hypothesis` | 基于属性的测试 |
| `black`, `ruff` | 代码风格 |
| `mypy` | 类型检查 |

---

## 17. 实现路线图

### 阶段 1：基础设施 ✅ 已完成

- [x] 项目骨架：`ea/`、`cli/` 目录、`_config.py`、`_types.py`
- [x] `_rng.py`：Xoshiro256StarStar + 种子 + shuffle
- [x] `_io.py`：read_file / read_file_subset / free_data
- [x] `_util.py`：所有工具函数 + rel_epsilon_equal + prediction_estimate
- [x] `_types.py`：Python dataclass 实现 TestCaseBase, IidTestCase, NonIidTestCase, IidTestRun, NonIidTestRun

### 阶段 2：简单估计器 ✅ 已完成

- [x] `mcv.py`
- [x] `collision.py`
- [x] `markov.py`
- [x] `compression.py`（含 Kahan 求和 + G 函数）

### 阶段 3：复杂估计器 ✅ 已完成

- [x] `_lrs.py`：纯 Python sorted() 后缀数组 + Kasai LCP + Kaufer 算法
- [x] `multi_mcw.py`
- [x] `lag_test.py`
- [x] `multi_mmc.py`（二进制 + 通用）
- [x] `lz78y.py`（二进制 + 通用）

### 阶段 4：IID 套件 ✅ 已完成

- [x] `chi_square.py`：scipy.gammaincc + 内置 _cephes_igamc 回退
- [x] `permutation.py`：19 项统计（顺序执行）
- [x] `iid_pipeline.py`：主流程

### 阶段 5：Restart + Conditioning ✅ 已完成

- [x] `restart.py`：simulate_bound + sanity + validation
- [x] `conditioning.py`：mpmath 任意精度计算

### 阶段 6：CLI + 集成测试 ✅ 已完成

- [x] 5 个 CLI 入口（ea_restart, ea_iid, ea_non_iid, ea_conditioning, ea_transpose）
- [x] JSON 输出（to_dict 手动转换）
- [x] 集成测试入口：`est_test/est_test_nist_c++_recode.py`

### 未实现项（性能优化）

> 每一项的实施耗时、回归机器时间、预计收益与资源占用（内存 / 磁盘 / 编译）已实测并汇总在
> `docs/优化候选清单与资源预算.md`，启动优化时以那份为准。

- [ ] `numba` 加速 `sa_algs`：四个在线预测器 JIT 后它就是最贵单 job（位串 11.8 s），也是最大内存户
      （单进程峰值 +419.8 MiB）。拆开实测是三段时间——Kaufer 扫描 56%、**列表化 Kasai 的 LCP 循环 31%**、
      numpy 后缀数组 13%，所以前两块 Python 循环要一起做。难点只在它的 `S` 用 Python int 当 uint128 用，
      numba 侧需退到 int64 并论证不溢出（4M 样本上 `n²/2 ≈ 8e12`，32M 样本上 `5.1e14`，均远小于 9.2e18；
      本次实测 4M 位串的 LCP 最大值 v = 42，累加数组只有 44 槽）。配套改动：`L` 不再 `.tolist()`
      而是把 int64 ndarray 直接喂进 kernel，顺带省掉约 137 MiB
- [ ] `numba` 加速通用字母表的 MultiMMC / LZ78Y（符号视图上分别还剩 8.4 s / 5.3 s）：两者是
      `dict` + `PostfixDictionary`，得先把它换成 njit 能吃的哈希表（`numba.typed.Dict` 或自写的
      开放寻址表），并逐字复现 `predict()` 的平局规则——改动量比前四个 kernel 大得多。
      字典条目 ~10⁶ 量级、现占 124 MiB，换成平铺表（int64 key + int32 count，λ=0.5）反而省 4–5 倍
- [ ] `numba` 加速 `permutation.py` 的碰撞检验（非二进制样本上占单轮 32%）；压缩检验本身是 C 级，无必要。
      **归属更正**：`permutation_tests` 只被 `iid_pipeline.py` 调用，它不在本节非 IID 的 30.4 s 里，
      而在 IID 路径的 44.8 s 里；且 njit 化会让每个 worker 各付 520 MiB commit，是内存负收益项
- [ ] （低优先）`libdivsufsort` ctypes 封装：后缀数组已降到 4M 位串 1.4–2.0 s，不再是关键路径

### 已实现的性能优化

- [x] `ProcessPoolExecutor` 并行化 Restart 模拟（`restart.py`）
- [x] `ProcessPoolExecutor` 并行化置换检验轮次（`permutation.py`，见 §8.4）
- [x] `ProcessPoolExecutor` 并行化非 IID 各估计（`non_iid_pipeline.py` + `ea/_parallel.py`，见 §14.4）：1M 字节样本端到端 141.2 s（`-j 1`）→ 56–59 s（4 进程以上的平台）
- [x] 后缀数组向量化：`_lrs.py` 用 numpy 前缀倍增 + 列表化 Kasai + 非稳定 argsort，把位串 t-Tuple+LRS 从 70 s 降到 11 s（§9.5、§14.3）
- [x] **可选 numba JIT**（`ea/_jit.py` + 四个预测器的纯 Python / kernel 双胞胎）：1M 字节样本端到端
      `-j 1` 142.6 s → 30.4 s、`-j 8` 61.3 s → 16.9 s，`H_assessed` 逐字相同（§14.1、§14.5）
- [x] 热循环去 numpy 标量化：`multi_mcw.py` 改用 Python 整数列表，`lag_test.py` 以“升序位置列表 + 二分裁剪”替掉参考实现的环形缓冲 struct（两者合计使 1M 字节样本的非 IID 串行从约 460 s 降到约 233 s，输出与 refdata 逐字节一致）
- [x] `multi_mmc.py` / `lz78y.py` 的符号流以 `bytes` 访问

### 关键里程碑

1. [x] `ea_non_iid` 在 `normal.bin` 上的完整输出与 refdata 完全对齐（允许 1e-6 偏差）
      —— 已达成并固化为回归工具：`refdata_diff.py --all --tol 1e-6` 11/11 样本通过（`normal.bin`
      是这 11 个之一），行数/字段名/行序零漂移，残余数值差异只有 §15.5 列的三类。严格 1e-9 档下
      3 个短样本 `exact = 53 / 89 / 87`
2. [ ] `ea_iid` 三件套（χ² + LRS + 置换）全部通过 —— **缺验收工具，无法判定**。`refdata_diff.py`
      只比对 `ea_non_iid -vv`，IID 侧至今没有端到端的 refdata 比对（C++ 的 `iid_main` 有 selftest
      基准可用）。这是 `docs/优化候选清单与资源预算.md` §4-A3 的前置缺口，补它约 30–60 min
3. [ ] `ea_restart` 通过自己构造的测试数据（1M 样本）—— 同样没有固化验收：`restart.py` 的实现
      与并行化都已完成（§11、§14.4），但仓库里没有构造好的 1M 样本测试数据与比对基准
4. [ ] ~~置换检验在 8 核机器上 60 秒内完成（需 numba + 并行化）~~ —— **目标不可达，需重新定义**。
      实测 1M 字节样本全量 10000 轮约 **21 min**（8 核并行；同机串行外推约 69 min），轮次并行已落地
      （§8.4、§14.4）但只拿到 3–5x（内存带宽墙）。剩余瓶颈不在 Python 循环上：单轮 19 项统计里
      **bz2 压缩检验占 56–82%**（0.36 s/轮，C 级实现，numba 无从加速），其次才是纯 Python 的碰撞检验
      （非二进制样本上 32%，即 A3 的靶子，上限 44.8→约 30–35 s）。要进 60 s 量级得换掉 bz2 那一档
      或削减轮数，都属改变参考实现口径，不在「优化」范围内
