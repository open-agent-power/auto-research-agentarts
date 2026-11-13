# Worker 主机接入与验收包

目的：为下一阶段准备可复查的主机资格检查。**这不是已实现的远程Worker服务或已完成的部署**；当前云机的隔离失败仍保留。不采购机器、不改宿主权限、不启动特权daemon，不把安装命令当成安装成功。

## 建议主机条件

Linux x86_64、cgroup v2、Python≥3.11、Docker及可用Unix socket。参考配置4CPU/16GiB，至少30GB可用磁盘；首轮不需要GPU。可使用正常配置的rootful Docker，或已由平台/管理员完成cpu/memory/pids委派的rootless Docker；无委派的rootless模式不合格。

预留控制器3–4GiB、至少5GiB磁盘余量；初期同时一个有界研究Worker。具体实际任务内存/CPU/PID/工件合同需监督器另外执行和验收。读取主机资源总额不能证明单Worker限制。

## 无副作用接入准备

1. 机器所有者在其信任边界内安装并配置Docker；本仓库不自动提权、修改系统或开放端口。
2. 将本仓库放到主机普通用户拥有的目录，保留固定commit。凭据通过受支持的安全环境/连接配置提供；模型/云密钥不传入资格探针容器。
3. 确认可访问所需镜像仓库。网络/CA/registry凭据由主机已有配置管理，保持TLS验证。探针运行时网络关闭。
4. 以下检查只需Docker socket访问权限和Python标准库，不安装项目科学依赖或调用模型。

```sh
sh deploy/worker/preflight.sh --help
sh deploy/worker/preflight.sh runs/worker-qualification-unique-id
```

封装只调用现有 `scripts/verify_cloud_resources.py`，固定小镜像digest，非root、只读根、无网络、移除capabilities及NoNewPrivs，要求真实容器内1CPU/512MiB/128PID以及1MiB tmpfs。stdout与JSON原件须保留；输出目录必须是新目录。

返回0表示该有界探针报告的10项检查均通过；返回2保持阻塞；64表示参数/证据目录不合规，未启动探针。其他非零退出也不是通过。`docker inspect`保存了请求参数不代表实际生效，必须查看容器内部cgroup原件。

## 主机通过后仍需完成的验收

- 根据实际任务固定CPU/RAM/PID/壁钟/网络与临时文件政策，并验证相应任务配置，而不只依赖小探针。
- 保持生产基线、评价器、隐藏数据、预算、晋级器与密钥不可被候选写入；禁止Docker socket/整宿主目录挂入不可信Worker。
- 实现并实测有界工件回传、内容身份、路径/符号链接处理、持久目录配额、超时/未知执行/幂等恢复。当前tmpfs测试不证明持久bind-mount配额。
- 在真正隔离环境完成所需上游最小PoC，保留成功/失败和许可决定。源码读取/AST检查不冒充runtime兼容。
- 独立复核后更新G0，才解锁依赖阶段。资格探针通过不等于G0/G2/G4或产品部署通过。

## 当前验证范围

此封装已进行shell语法、帮助和已有目录拒绝检查；没有远程服务器、采购、安装或部署发生。当前云机已知不支持所需cgroup，未为测试封装再跑同一个失败容器。实际Worker地址、连接授权和主机资格证据仍待接入。
