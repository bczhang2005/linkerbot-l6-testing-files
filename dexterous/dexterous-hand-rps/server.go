package main

import (
	"bytes"
	"embed"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log"
	"mime"
	"net/http"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

//go:embed 1.detect-hand-shape 2.detect-hand-rps 3.output-event 4.follow-me 5.always-win 6.gameplay 7.follow-me-3d shared index.html
var content embed.FS

// CAN 服务器配置
const canServerURL = "http://localhost:5260/api/can"
const maxCanHTTPConcurrency = 16

// HTTP 客户端（复用连接）
var httpClient *http.Client
var httpClientOnce sync.Once
var canHTTPSemaphore = make(chan struct{}, maxCanHTTPConcurrency)

// 型号过滤配置（命令行参数）
var modelFilter string

// L25 串行队列：加锁 + 单槽 pending（只保留最新，执行完整个序列后才响应下一个）
var l25Queue struct {
	mu        sync.Mutex
	executing bool
	pending   *ModelDeviceConfig // 待执行的下一序列，nil 表示无
}

// 初始化 HTTP 客户端，复用连接
func getHTTPClient() *http.Client {
	httpClientOnce.Do(func() {
		// 配置连接池参数，复用 HTTP 连接
		transport := &http.Transport{
			MaxIdleConns:        200,              // 最大空闲连接数
			MaxIdleConnsPerHost: 64,               // 每个主机最大空闲连接数
			MaxConnsPerHost:     64,               // 限制同一主机总连接，避免洪峰耗尽资源
			IdleConnTimeout:     90 * time.Second, // 空闲连接超时时间
			DisableKeepAlives:   false,            // 启用连接复用
		}

		httpClient = &http.Client{
			Transport: transport,
			Timeout:   3 * time.Second, // 请求超时时间，避免堆积时恢复过慢
		}
	})
	return httpClient
}

// CAN 消息结构
type CanMessage struct {
	Interface string `json:"interface"`
	ID        int    `json:"id"`
	Data      []int  `json:"data"`
}

// 型号设备配置结构
type ModelDeviceConfig struct {
	Interface []string `json:"interface"` // CAN接口列表，如 ["can0", "can1"]
	ID        []int    `json:"id"`        // CAN ID列表，每个元素对应一个interface的ID（与interface一一对应，可选，默认为1）
	Data      DataType `json:"data"`      // 数据，支持两种格式：单个数组或数组数组，每个数组发送给所有interface
}

// 数据类型：支持单个数组或数组数组
type DataType [][]int

// 自定义JSON解析，支持单个数组和数组数组两种格式
func (d *DataType) UnmarshalJSON(data []byte) error {
	// 先尝试解析为数组数组
	var arrayArray [][]int
	if err := json.Unmarshal(data, &arrayArray); err == nil {
		*d = arrayArray
		return nil
	}

	// 如果失败，尝试解析为单个数组
	var singleArray []int
	if err := json.Unmarshal(data, &singleArray); err == nil {
		*d = [][]int{singleArray}
		return nil
	}

	return fmt.Errorf("无法解析data字段，必须是数组或数组数组")
}

// 按型号分组的请求结构
type GestureRequest struct {
	// 键为型号（如 "l10", "l6"），值为该型号的配置
	Models map[string]ModelDeviceConfig `json:"models"`
}

// 批量发送响应结构
type BatchCanResponse struct {
	Status  string   `json:"status"`
	Success int      `json:"success"`
	Failed  int      `json:"failed"`
	Errors  []string `json:"errors,omitempty"`
	Message string   `json:"message,omitempty"`
}

// FollowDeviceEntry 跟随模式单设备载荷（每接口独立 CAN，支持左右手不同数据）
type FollowDeviceEntry struct {
	Model     string  `json:"model"`
	Interface string  `json:"interface"`
	ID        int     `json:"id"`
	Data      [][]int `json:"data"`
}

// FollowBatchRequest POST /api/follow/batch 请求体
type FollowBatchRequest struct {
	Devices []FollowDeviceEntry `json:"devices"`
}

func main() {
	// 命令行参数：端口号和型号过滤
	port := flag.Int("port", 8899, "服务器端口号")
	flag.StringVar(&modelFilter, "model", "", "过滤型号（如: l10, O6），默认处理所有型号")
	flag.Parse()

	// 注册额外的 MIME 类型
	mime.AddExtensionType(".js", "application/javascript")
	mime.AddExtensionType(".wasm", "application/wasm")
	mime.AddExtensionType(".tflite", "application/octet-stream")
	mime.AddExtensionType(".binarypb", "application/octet-stream")

	// 创建文件服务器
	fsys, err := fs.Sub(content, ".")
	if err != nil {
		log.Fatal(err)
	}

	// 自定义文件服务器，添加正确的 MIME 类型
	fileServer := http.FileServer(http.FS(fsys))

	// 按型号批量发送 CAN 消息 API（新架构：二级协程处理）
	http.HandleFunc("/api/gesture/batch", handleGestureBatch)
	// 关节跟随：每设备独立 data，高频下发（与 gesture/batch 分离，便于限流与监控）
	http.HandleFunc("/api/follow/batch", handleFollowBatch)

	// 包装文件服务器，添加日志和 MIME 类型处理
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// 记录请求
		log.Printf("%s %s", r.Method, r.URL.Path)

		// 根据文件扩展名设置正确的 Content-Type
		ext := filepath.Ext(r.URL.Path)
		switch ext {
		case ".js":
			w.Header().Set("Content-Type", "application/javascript; charset=utf-8")
		case ".wasm":
			w.Header().Set("Content-Type", "application/wasm")
		case ".tflite":
			w.Header().Set("Content-Type", "application/octet-stream")
		case ".binarypb":
			w.Header().Set("Content-Type", "application/octet-stream")
		case ".data":
			w.Header().Set("Content-Type", "application/octet-stream")
		case ".css":
			w.Header().Set("Content-Type", "text/css; charset=utf-8")
		case ".html":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
		}

		// 提供文件
		fileServer.ServeHTTP(w, r)
	})

	// 启动服务器
	addr := fmt.Sprintf(":%d", *port)
	log.Printf("🚀 灵巧手剪刀石头布游戏服务器启动")
	log.Printf("📡 监听地址: http://localhost%s", addr)
	if modelFilter != "" {
		log.Printf("🔍 型号过滤: %s (只处理匹配的型号，支持逗号分隔多型号)", modelFilter)
	} else {
		log.Printf("🔍 型号过滤: 全部型号")
	}
	log.Printf("🌐 访问主页: http://localhost%s/", addr)
	log.Printf("💡 提示: 按 Ctrl+C 停止服务器")
	log.Printf("")
	log.Printf("📂 可用页面:")
	log.Printf("   - http://localhost%s/              (主页)", addr)
	log.Printf("   - http://localhost%s/1.detect-hand-shape/", addr)
	log.Printf("   - http://localhost%s/2.detect-hand-rps/", addr)
	log.Printf("   - http://localhost%s/3.output-event/", addr)
	log.Printf("   - http://localhost%s/4.follow-me/", addr)
	log.Printf("   - http://localhost%s/7.follow-me-3d/     (RealSense D405 3D 跟随)", addr)
	log.Printf("   - http://localhost%s/5.always-win/", addr)
	log.Printf("   - http://localhost%s/6.gameplay/", addr)
	log.Printf("📡 API: POST /api/gesture/batch  ·  POST /api/follow/batch（跟随）")
	log.Printf("")

	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatal(err)
	}
}

// 处理按型号批量发送 CAN 消息请求（二级协程架构）
func handleGestureBatch(w http.ResponseWriter, r *http.Request) {
	// 只允许 POST 请求
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// 设置响应头
	w.Header().Set("Content-Type", "application/json; charset=utf-8")

	// 解析请求体
	var req GestureRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		response := BatchCanResponse{
			Status:  "error",
			Success: 0,
			Failed:  0,
			Message: fmt.Sprintf("解析请求失败: %v", err),
		}
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(response)
		return
	}

	// 验证请求
	if len(req.Models) == 0 {
		response := BatchCanResponse{
			Status:  "error",
			Success: 0,
			Failed:  0,
			Message: "型号列表为空",
		}
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(response)
		return
	}

	// 根据命令行参数过滤型号
	filteredModels := make(map[string]ModelDeviceConfig)
	for modelName, modelConfig := range req.Models {
		if shouldProcessModel(modelName) {
			filteredModels[modelName] = modelConfig
		} else {
			log.Printf("⏭️  跳过型号 %s (不匹配过滤条件: %s)", modelName, modelFilter)
		}
	}

	// 如果过滤后没有型号，返回提示
	if len(filteredModels) == 0 {
		response := BatchCanResponse{
			Status:  "ok",
			Success: 0,
			Failed:  0,
			Message: fmt.Sprintf("没有匹配过滤条件 '%s' 的型号", modelFilter),
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(response)
		return
	}

	// 全局统计
	var globalWg sync.WaitGroup
	var globalMu sync.Mutex
	successCount := 0
	failedCount := 0
	var errors []string

	// 第一级协程：为每个型号启动一个协程
	for modelName, modelConfig := range filteredModels {
		globalWg.Add(1)
		go processModel(modelName, modelConfig, &globalWg, &globalMu, &successCount, &failedCount, &errors)
	}

	// 等待所有型号处理完成
	globalWg.Wait()

	// 构建响应
	response := BatchCanResponse{
		Status:  "ok",
		Success: successCount,
		Failed:  failedCount,
	}

	if len(errors) > 0 {
		response.Errors = errors
	}

	// 只在全部成功时打印一条简洁日志，失败时打印详细信息
	if failedCount == 0 {
		log.Printf("✓ 批量发送成功: %d 条消息", successCount)
	} else {
		log.Printf("⚠ 批量发送完成: 成功 %d, 失败 %d", successCount, failedCount)
	}

	// 返回响应
	if failedCount > 0 {
		w.WriteHeader(http.StatusPartialContent) // 部分成功
	} else {
		w.WriteHeader(http.StatusOK)
	}
	json.NewEncoder(w).Encode(response)
}

// handleFollowBatch 处理跟随模式：对每个设备的每条 data 行发送一条 CAN（不做 L25 帧队列）
func handleFollowBatch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")

	var req FollowBatchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(BatchCanResponse{
			Status:  "error",
			Message: fmt.Sprintf("解析请求失败: %v", err),
		})
		return
	}

	if len(req.Devices) == 0 {
		json.NewEncoder(w).Encode(BatchCanResponse{
			Status:  "ok",
			Success: 0,
			Failed:  0,
			Message: "devices 为空",
		})
		return
	}

	var wg sync.WaitGroup
	var mu sync.Mutex
	successCount := 0
	failedCount := 0
	var errs []string

	for i := range req.Devices {
		dev := req.Devices[i]
		if !shouldProcessModel(dev.Model) {
			continue
		}
		if dev.Interface == "" || len(dev.Data) == 0 {
			mu.Lock()
			failedCount++
			errs = append(errs, fmt.Sprintf("型号 %s: 接口或 data 为空", dev.Model))
			mu.Unlock()
			continue
		}

		wg.Add(1)
		go func(dev FollowDeviceEntry) {
			defer wg.Done()
			// 同一设备的多行 CAN 必须保持顺序，避免 finger/palm 帧被乱序下发。
			for di, row := range dev.Data {
				if len(row) == 0 {
					mu.Lock()
					failedCount++
					errs = append(errs, fmt.Sprintf("%s data[%d] 为空", dev.Model, di))
					mu.Unlock()
					continue
				}

				ok := sendCanMessage(CanMessage{Interface: dev.Interface, ID: dev.ID, Data: row})
				mu.Lock()
				if ok {
					successCount++
				} else {
					failedCount++
					errs = append(errs, fmt.Sprintf("跟随 %s %s [%d]", dev.Model, dev.Interface, di))
				}
				mu.Unlock()
			}
		}(dev)
	}

	wg.Wait()

	resp := BatchCanResponse{
		Status:  "ok",
		Success: successCount,
		Failed:  failedCount,
	}
	if len(errs) > 0 {
		resp.Errors = errs
	}
	if failedCount > 0 && successCount == 0 {
		w.WriteHeader(http.StatusPartialContent)
	} else if failedCount > 0 {
		w.WriteHeader(http.StatusPartialContent)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	json.NewEncoder(w).Encode(resp)
}

// 获取 CAN ID（如果提供了ID列表则使用，否则使用默认值1）
func getCanID(ids []int, index int) int {
	if len(ids) > index {
		return ids[index]
	}
	return 1 // 默认ID
}

// 检查单个型号关键字是否匹配实际型号名称
func matchModel(keyword, model string) bool {
	switch keyword {
	case "l10":
		return strings.HasPrefix(model, "l10")
	case "o6", "l6":
		return model == "o6/l6" || model == "o6" || model == "l6"
	case "l25":
		return model == "l25"
	default:
		return model == keyword
	}
}

// 检查型号是否匹配过滤条件（支持逗号分隔的多型号，如 "l10,o6,l25"）
func shouldProcessModel(modelName string) bool {
	// 如果没有设置过滤条件，处理所有型号
	if modelFilter == "" {
		return true
	}

	model := strings.ToLower(modelName)

	// 按逗号分割，遍历每个关键字，任意匹配则通过
	for _, kw := range strings.Split(modelFilter, ",") {
		keyword := strings.TrimSpace(strings.ToLower(kw))
		if keyword != "" && matchModel(keyword, model) {
			return true
		}
	}

	return false
}

// 处理单个型号的设备（封装为函数，支持二级协程架构）
func processModel(
	model string,
	config ModelDeviceConfig,
	globalWg *sync.WaitGroup,
	globalMu *sync.Mutex,
	successCount *int,
	failedCount *int,
	errors *[]string,
) {
	defer globalWg.Done()

	// L25 使用串行队列：加锁 + 单槽 pending，只执行最新，执行完整个序列后才响应下一个
	if strings.ToLower(model) == "l25" {
		processL25WithQueue(&config, globalMu, successCount, failedCount, errors)
		return
	}

	// 其他型号：原有并发逻辑
	executeModelConfig(model, config, globalMu, successCount, failedCount, errors)
}

// L25 串行队列处理：正在执行时新请求入栈（替换旧的），执行完整个序列后才处理栈内下一个
func processL25WithQueue(
	config *ModelDeviceConfig,
	globalMu *sync.Mutex,
	successCount *int,
	failedCount *int,
	errors *[]string,
) {
	// 验证配置
	if len(config.Interface) == 0 || len(config.Data) == 0 {
		globalMu.Lock()
		*failedCount++
		*errors = append(*errors, "型号 L25: 接口或数据为空")
		globalMu.Unlock()
		return
	}
	if len(config.ID) > 0 && len(config.ID) != len(config.Interface) {
		globalMu.Lock()
		*failedCount++
		*errors = append(*errors, "型号 L25: ID数量与接口数量不匹配")
		globalMu.Unlock()
		return
	}

	l25Queue.mu.Lock()
	if l25Queue.executing {
		// 正在执行：将当前请求入栈（替换旧的，丢弃超出的）
		l25Queue.pending = config
		l25Queue.mu.Unlock()
		return // 本请求被丢弃/替换，不执行
	}
	l25Queue.executing = true
	l25Queue.mu.Unlock()

	// 循环：执行当前 config，完成后检查 pending，有则继续执行
	for {
		executeModelConfig("L25", *config, globalMu, successCount, failedCount, errors)

		l25Queue.mu.Lock()
		l25Queue.executing = false
		if l25Queue.pending != nil {
			config = l25Queue.pending
			l25Queue.pending = nil
			l25Queue.executing = true
			l25Queue.mu.Unlock()
			continue
		}
		l25Queue.mu.Unlock()
		break
	}
}

// 执行单个型号的 CAN 发送逻辑（不含 L25 队列）
func executeModelConfig(
	model string,
	config ModelDeviceConfig,
	globalMu *sync.Mutex,
	successCount *int,
	failedCount *int,
	errors *[]string,
) {
	// 验证配置
	if len(config.Interface) == 0 || len(config.Data) == 0 {
		globalMu.Lock()
		*failedCount++
		*errors = append(*errors, fmt.Sprintf("型号 %s: 接口或数据为空", model))
		globalMu.Unlock()
		return
	}
	if len(config.ID) > 0 && len(config.ID) != len(config.Interface) {
		globalMu.Lock()
		*failedCount++
		*errors = append(*errors, fmt.Sprintf("型号 %s: ID数量(%d)与接口数量(%d)不匹配", model, len(config.ID), len(config.Interface)))
		globalMu.Unlock()
		return
	}

	var modelWg sync.WaitGroup
	var modelMu sync.Mutex
	modelSuccess := 0
	modelFailed := 0

	for i, iface := range config.Interface {
		modelWg.Add(1)
		go func(interfaceName string, canID int) {
			defer modelWg.Done()
			// 同一接口内按 data 顺序发送，避免多帧动作被并发乱序。
			for dataIndex, dataArray := range config.Data {
				canMsg := CanMessage{Interface: interfaceName, ID: canID, Data: dataArray}
				if sendCanMessage(canMsg) {
					modelMu.Lock()
					modelSuccess++
					modelMu.Unlock()
				} else {
					modelMu.Lock()
					modelFailed++
					modelMu.Unlock()
					globalMu.Lock()
					*errors = append(*errors, fmt.Sprintf("型号 %s, 接口 %s, 数据[%d]: 发送失败", model, interfaceName, dataIndex))
					globalMu.Unlock()
				}
			}
		}(iface, getCanID(config.ID, i))
	}

	modelWg.Wait()

	globalMu.Lock()
	*successCount += modelSuccess
	*failedCount += modelFailed
	globalMu.Unlock()
}

// 发送单个 CAN 消息到 CAN 服务器
func sendCanMessage(msg CanMessage) bool {
	client := getHTTPClient()

	// 序列化消息
	jsonData, err := json.Marshal(msg)
	if err != nil {
		return false
	}

	// 创建请求
	req, err := http.NewRequest("POST", canServerURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return false
	}
	req.Header.Set("Content-Type", "application/json")

	canHTTPSemaphore <- struct{}{}
	defer func() { <-canHTTPSemaphore }()

	// 发送请求（复用连接）
	resp, err := client.Do(req)
	if err != nil {
		return false
	}
	defer func() {
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}()

	// 检查响应
	if resp.StatusCode == http.StatusOK {
		var result map[string]interface{}
		if err := json.NewDecoder(resp.Body).Decode(&result); err == nil {
			if status, ok := result["status"].(string); ok && status == "success" {
				return true
			}
		}
	}

	return false
}
