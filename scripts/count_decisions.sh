#!/bin/bash

# Count rows where decision is "maybe" or "relevant"
# Usage: ./count_decisions.sh judge_decisions.csv

awk -F',' 'NR==1 {for(i=1;i<=NF;i++) if($i=="decision") col=i; next} $col=="maybe" || $col=="relevant" {count++} END {print count}' "$1"