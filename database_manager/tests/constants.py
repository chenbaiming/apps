"""仅用于测试的固定格式 Fernet 密钥。"""

from cryptography.fernet import Fernet


# 每个测试进程动态生成密钥，既不提交真实生产密钥，也满足 Fernet 格式要求。
TEST_FERNET_KEY = Fernet.generate_key().decode("ascii")
