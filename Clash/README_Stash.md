# Stash 原生 Provider 模板

`ClashRule_Stash.ini` 用于 SubConverter-Extended 的 `target=stash`，底板为同目录的 `base_stash.yaml`。

## TAG 独立更新

在 Subweb 中选择 **SubConverter-Extended → Stash → LovinYarn · Stash**，添加 Provider：

| 字段 | 值 |
| --- | --- |
| Provider 名称 | `TAG` |
| 来源标签 | 留空，只有按来源标签分组时才需要填写 |
| 订阅 URL | 能由 Stash 设备直接访问的订阅地址，正文应为 Stash 兼容的 Provider YAML |
| 独立更新间隔 | `21600`，单位为秒，即 6 小时 |

添加到来源后，应生成以下形式（用自己的订阅替换示例地址）：

```text
provider:TAG,interval:21600,https://example.com/sub
```

`21600` 是单条 Provider 的更新间隔，通过来源前缀传入；不等同于托管配置的 `interval` 查询参数。未填写 Provider 间隔时使用后端默认值。

生成结果应包含：

```yaml
proxy-providers:
  TAG:
    url: https://example.com/sub
    path: ./providers/TAG.yaml
    interval: 21600
```

地区组通过 `use: [TAG]` 和分组过滤条件动态选择节点。后端不再下载并内联订阅节点，Stash 按自己的更新时间读取 Provider，因此在局域网地址作为订阅来源时，Stash 设备也需要能访问对应局域网。

## 保持原生模式

模板保留地区分组、业务策略和分流规则，关闭模板级节点排除、Emoji 改写和废弃节点过滤。这些需要服务端处理节点的操作会让 Extended 回退到普通节点转换。

使用完整配置，不启用“仅输出节点”。高级选项中的节点重命名、Emoji、排序、统一 UDP/TFO/TLS 等覆盖保持“跟随后端”，避免显式请求节点改写。节点名称及节点自身参数由订阅提供；地区过滤由 Stash 的策略组执行。

可使用 Extended 的 `explain=true` 诊断：原生模式应显示 `remote_subscription_backend: stash-proxy-provider`、`remote_subscription_reason: native-capable`，且 `provider_count` 大于零。
