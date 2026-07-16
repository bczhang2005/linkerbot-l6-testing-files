# 灵巧手剪刀石头布游戏 

## 快速开始

### 1. 开发模式（直接运行）

```bash
# 方法 1: 使用 go run (需要 Go 环境)
go run server.go

# 方法 2: 使用 Python (传统方式)
python -m http.server 8080
```

### 2. 构建可执行文件

#### Linux

```bash

# 或者只构建当前平台
go build  -ldflags="-s -w" -o dexterous-hand-rps server.go

# 运行
./dexterous-hand-rps

# 自定义端口
./dexterous-hand-rps -port 3000
```

## 使用说明

### 启动服务器

```bash
# 默认端口 8080
./dexterous-hand-rps-linux-amd64

# 自定义端口
./dexterous-hand-rps-linux-amd64 -port 3000
```

### 访问页面

服务器启动后，在浏览器中访问：

- 主页: http://localhost:8080/
- 手势检测: http://localhost:8080/1.detect-hand-shape/
- 剪刀石头布识别: http://localhost:8080/2.detect-hand-rps/
- 事件输出: http://localhost:8080/3.output-event/
- 跟随模式: http://localhost:8080/4.follow-me/
- 必胜模式: http://localhost:8080/5.always-win/
- 游戏模式: http://localhost:8080/6.gameplay/


### 编译优化

使用 `-ldflags="-s -w"` 减小可执行文件大小：
- `-s` 去除符号表
- `-w` 去除 DWARF 调试信息

## 故障排除

### 端口被占用

```bash
# 查看端口占用
lsof -i :8080  # Linux/macOS
netstat -ano | findstr :8080  # Windows

# 使用其他端口
./dexterous-hand-rps -port 8090
```

### 权限问题（Linux/macOS）

```bash
# 添加执行权限
chmod +x dexterous-hand-rps-linux-amd64
```

### 跨平台编译问题

确保安装了 Go 1.16 或更高版本：

```bash
go version
```




## 许可证

本项目遵循项目根目录的 LICENSE 文件。

