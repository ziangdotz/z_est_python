"""NIST SP 800-90B Entropy Assessment - Global Constants"""

# Sample size and test parameters
MIN_SIZE = 1_000_000
PERMS = 10_000
ZALPHA = 2.5758293035489008
ITERMAX = 1076

# Lag prediction test
D_LAG = 128

# MultiMMC test
D_MMC = 16

# LZ78Y test
B_len = 16
MAX_DICTIONARY_SIZE = 65536

# MultiMCW test
NUM_WINS = 4
W = [63, 255, 1023, 4095]

# Dictionary limits
MAX_ENTRIES = 100_000

# Restart test
DEFAULT_SIM_ROUNDS = 5_000_000

# Suffix array limit
SAINDEX_MAX = 2**31 - 1  # INT32_MAX

# Floating point constants
DBL_EPSILON = 2.220446049250313e-16
DBL_MIN = 2.2250738585072014e-308

# Permutation test count
NUM_TESTS = 19
