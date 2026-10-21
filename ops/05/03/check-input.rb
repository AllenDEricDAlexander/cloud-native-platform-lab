#!/usr/bin/env ruby
require_relative "../lib/config"
categories = %w[ceph vsphere postgresql redis kafka rabbitmq nats gitlab jenkins harbor nexus]
sources = required("sources")
abort "完整采集尚缺类别：#{(categories-sources.map { |s| s['category'] }).join(',')}" unless (categories-sources.map { |s| s["category"] }).empty?
abort "每个源必须声明实际信号查询" unless sources.all? { |s| s["id"].to_s.match?(/\A[a-z][a-z0-9-]{2,40}\z/) && s["checks"].is_a?(Array) && !s["checks"].empty? && s["checks"].all? { |e| e.is_a?(String) && !e.include?("\n") } }
