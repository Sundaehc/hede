# Codex 配置MCP

在 Windows PowerShell 中执行（使用管理员签发的个人 Token）：

```powershell
$secret = Read-Host "粘贴 MCP Token" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    [Environment]::SetEnvironmentVariable(
        "HEDE_MCP_TOKEN",
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer),
        "User"
    )
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
```

关闭并重新打开 PowerShell，然后执行：

```powershell
codex mcp add hede_readonly --url https://platform.hedespace.com/mcp --bearer-token-env-var HEDE_MCP_TOKEN
codex mcp list
codex
```

上述 `codex mcp add` 会在 `%USERPROFILE%\.codex\config.toml` 中生成配置。也可直接编辑该文件，已有同名段落时不要重复添加：

```toml
[mcp_servers.hede_readonly]
url = "https://platform.hedespace.com/mcp"
bearer_token_env_var = "HEDE_MCP_TOKEN"
tool_timeout_sec = 30
```
