#!/bin/bash
# Fix CentOS 7 EOL repos + install Docker CE via Aliyun
set -euo pipefail

fix_centos_repos() {
  if [ -f /etc/yum.repos.d/CentOS-Base.repo ]; then
    cp -a /etc/yum.repos.d/CentOS-Base.repo "/etc/yum.repos.d/CentOS-Base.repo.bak.$(date +%s)" || true
  fi
  cat >/etc/yum.repos.d/CentOS-Base.repo <<'EOF'
[base]
name=CentOS-7 - Base - Aliyun vault
baseurl=https://mirrors.aliyun.com/centos-vault/7.9.2009/os/$basearch/
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
enabled=1

[updates]
name=CentOS-7 - Updates - Aliyun vault
baseurl=https://mirrors.aliyun.com/centos-vault/7.9.2009/updates/$basearch/
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
enabled=1

[extras]
name=CentOS-7 - Extras - Aliyun vault
baseurl=https://mirrors.aliyun.com/centos-vault/7.9.2009/extras/$basearch/
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
enabled=1

[centosplus]
name=CentOS-7 - Plus - Aliyun vault
baseurl=https://mirrors.aliyun.com/centos-vault/7.9.2009/centosplus/$basearch/
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
enabled=0
EOF
  yum clean all
  yum makecache || true
}

if command -v docker >/dev/null 2>&1; then
  echo "Docker already installed: $(docker --version)"
  systemctl enable docker
  systemctl start docker || true
  exit 0
fi

fix_centos_repos
yum install -y yum-utils device-mapper-persistent-data lvm2
yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
sed -i 's+download.docker.com+mirrors.aliyun.com/docker-ce+' /etc/yum.repos.d/docker-ce.repo || true
yum install -y docker-ce docker-ce-cli containerd.io
systemctl enable docker
systemctl start docker

mkdir -p /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com"
  ]
}
EOF
systemctl daemon-reload
systemctl restart docker
docker --version
echo "Docker install OK"
