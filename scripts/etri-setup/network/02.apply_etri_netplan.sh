#!/bin/bash

echo "=== ETRI Netplan 설정 적용 ==="

# root 권한 확인
if [ "$EUID" -ne 0 ]; then
    echo "root 권한 필요: sudo ./02.apply_etri_netplan.sh"
    exit 1
fi

# 스크립트 위치 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_YAML="${SCRIPT_DIR}/yaml/netplan/etri-50-cloud-init.yaml"
TARGET_YAML="/etc/netplan/50-cloud-init.yaml"

# 소스 파일 존재 확인
if [ ! -f "$SOURCE_YAML" ]; then
    echo "❌ 소스 파일을 찾을 수 없습니다: $SOURCE_YAML"
    exit 1
fi

# netplan 파일 복사
echo "ETRI netplan 설정 적용 중..."
cp "$SOURCE_YAML" "$TARGET_YAML"

# netplan 적용
echo "netplan 설정 적용 중..."
netplan apply

echo "✅ ETRI netplan 설정 적용 완료"
echo "   - 대상 파일: $TARGET_YAML"


