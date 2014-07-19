#! /bin/sh

######################################################################
#
# GET_STOCKQTYS.SH
# 持ち出し可能な在庫数を得る
# Written by Matsuura(richmikan@richlab.org) at 2013/12/21
#
# [引数] GET_STOCKQTYS.SH <商品ID> [<商品ID> ...]
# ・指定された各々の<商品ID>について、商品マスター表と在庫数ファイルの
#   情報に基づき、報現在持ち出し可能な在庫数の一覧表を返す。
#
# [出力]
#  1:商品ID 2:持ち出し可能在庫数
#
# [備考]
# ・与えられた商品IDが商品マスター表にない場合は無視される。
# ・電子版等、無限在庫の場合は2列目を"*"にして返す。
# ・指定商品が、別の商品在庫数に依存している場合、そのうちの最少のもの
#   を返す。例えば、SHOCCAR_MAG定期購読セットがVol.0～3の在庫数に依存し
#   ており、Vol.0が最も少なくて在庫10だった場合、10を返す。
#   (この在庫数依存関係の定義は、商品マスター表で行う)
#
# [注意]
# ・在庫数は刻々と変化するため。この値は時間経過と共に、最新の値からず
#   れていく。そのため目安としてのみ扱うこと、
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB  # Tukubaiパス、その他共通定義
. $Homedir/CONFIG/TRADING.SHLIB # 取り引きルール
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- その他各種設定 -------------------------------------------------
readonly INFI_STOCK=10000000000 # 在庫数=無限と見なす場合の便宜的な値(100億)

# --- エラー終了関数定義 ---------------------------------------------
error_exit() {
  [ -n "$2" ] && echo "${0##*/}: $2" 1>&2
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit $1
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -z "$DISABLE_SHLOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/SHELL
  ([ "$SUEXEC_MODE" -eq 0 ] && umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || error_exit 1 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error_exit 1 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error_exit 1 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# 確認
######################################################################

# 引数の数は合っているか？
[ $# -gt 0 ] || error_exit 1 'No arguments, see the usage'

# 商品マスター表ファイルはあるか？
[ -f "$File_PRODUCTS" ] || error_exit 2 'The product master file is not found'

# 在庫数ファイルディレクトリーはあるか？
[ -d "$Dir_STOCK"  ] || error_exit 3 'The product quantity dir. is not found'


######################################################################
# メイン
######################################################################

# --- 在庫数確認要求商品IDリストファイルを作成------------------------
echo "$@"   |
tr ' ' '\n' |
sort        > $Tmp-reqproductlist # 1:確認したい商品ID

# --- 現在在庫数リストファイルを作成 ---------------------------------
(cd "$Dir_STOCK"; ls -l) |
tail -n +2               |
self 9 5                 > $Tmp-stockqty # 1:商品ID 2:現在在庫数

# --- 確認したい在庫数一覧表を出力する -------------------------------
cat "$File_PRODUCTS"                               |
env - sed 's/^#.*$//'                              | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'              | # コメント除去2
grep -v '^[[:blank:]]*$'                           | # 空行除去
self 1 6                                           |
# 1:商品ID* 2:在庫情報体                           #
sort -k1,1                                         |
#join0 key=1 $Tmp-reqproductlist                    |
join -1 1 -2 1 -o 2.1,2.2 $Tmp-reqproductlist -    |
# 1:商品ID* 2:在庫情報体 (マスターにある行のみ)    #
tr , ' '                                           |
# 1:商品ID* 2:在庫情報(1) [3:在庫情報(2) ...]      #
tarr num=1                                         |
# 1:商品ID 2:在庫情報                              #
awk '$2=="@"{$2=$1} {print}'                       | # 在庫情報"@"の意味を具体化(自身のIDで在庫数を管理していることを明示)
# 1:商品ID 2:在庫数参照先                          #
sort -k2,2 -k1,1                                   |
#join2 +0 key=2 $Tmp-stockqty                       | # 現在の在庫数表とRIGHT JOIN(レコード無しの場合は在庫数0とみなす)
join -1 1 -2 2 -a 2 -o 2.1,2.2,1.2 $Tmp-stockqty - |
sed 's/ $/ 0/'                                     |
# 1:商品ID 2:在庫数参照先 3:現在庫数               #
awk '$2=="*"{$3='$INFI_STOCK'} {print}'            | # 無限在庫品の場合は便宜的に設定された無限在庫数を設定
self 1 3                                           |
# 1:商品ID 2:現在庫数                              #
sort -k1,1 -k2n,2                                  | # 各商品を各依存商品の現在庫数で昇順ソートし
getfirst 1 1                                       | # 各商品の先頭行を取り出せば、最小値がわかる
# 1:商品ID* 2:現在庫数(最少)                       #
awk '$2=="'$INFI_STOCK'"{$2="*"} {print}'


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
