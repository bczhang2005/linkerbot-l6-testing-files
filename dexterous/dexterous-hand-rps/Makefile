SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

.DEFAULT_GOAL := help

.PHONY: help status sync new push merged clean-merged delete-local delete-local-force delete-remote cleanup diff-main log-main

help:
	@echo "可用命令："
	@echo "  make status                         查看当前仓库状态"
	@echo "  make sync                           切回 main 并拉取最新代码"
	@echo "  make new name=fix-xxx               基于 main 创建新分支"
	@echo "  make push                           推送当前分支到 origin"
	@echo "  make merged                         查看已经合并到 main 的本地分支"
	@echo "  make clean-merged                   清理已经合并到 main 的本地分支"
	@echo "  make delete-local branch=fix-xxx    删除指定本地分支"
	@echo "  make delete-local-force branch=fix-xxx 强制删除指定本地分支"
	@echo "  make delete-remote branch=fix-xxx   删除指定远端分支"
	@echo "  make cleanup branch=fix-xxx         删除本地和远端指定分支"
	@echo "  make diff-main                      查看当前分支与 origin/main 的差异"
	@echo "  make log-main                       查看当前分支相对 origin/main 的提交"

status:
	git status -sb
	git branch -vv
	git remote -v

sync:
	git switch main
	git pull --ff-only origin main
	git fetch --prune

new:
	@test -n "$(name)" || (echo "缺少分支名：make new name=fix-xxx" && exit 1)
	git switch main
	git pull --ff-only origin main
	git switch -c "$(name)"

push:
	git push -u origin "$$(git branch --show-current)"

merged:
	git branch --merged main

clean-merged:
	git switch main
	git pull --ff-only origin main
	git branch --merged main | grep -vE '^\*|^[[:space:]]*main$$|^[[:space:]]*master$$|^[[:space:]]*dev$$|^[[:space:]]*develop$$' | xargs -r git branch -d

delete-local:
	@test -n "$(branch)" || (echo "缺少分支名：make delete-local branch=fix-xxx" && exit 1)
	git branch -d "$(branch)"

delete-local-force:
	@test -n "$(branch)" || (echo "缺少分支名：make delete-local-force branch=fix-xxx" && exit 1)
	git branch -D "$(branch)"

delete-remote:
	@test -n "$(branch)" || (echo "缺少分支名：make delete-remote branch=fix-xxx" && exit 1)
	git push origin --delete "$(branch)"

cleanup:
	@test -n "$(branch)" || (echo "缺少分支名：make cleanup branch=fix-xxx" && exit 1)
	git switch main
	git pull --ff-only origin main
	git branch -d "$(branch)"
	git push origin --delete "$(branch)"

diff-main:
	git fetch origin
	git diff origin/main...HEAD

log-main:
	git fetch origin
	git log --oneline origin/main..HEAD