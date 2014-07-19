#! /bin/sh

######################################################################
#
# TAKEOUT_STOCKS.SH
# 在庫持ち出し
# Written by Matsuura(richmikan@richlab.org) at 2013/10/20
#
# [引数] TAKEOUT_STOCKS.SH <商品ID>:<要求数> [<商品ID>:<要求数> ...]
# ・<商品ID> の在庫数を <要求数> だけ減らす。(複数商品対応)
#
# [出力]
# ・成功した時は $?=0 で、標準出力には何も出力しない。
# ・在庫不足で失敗した時には $?=1 で、標準出力に次の内容を出力する。
#   insufficient-stock: <足りなかった商品ID>,<足りなかった商品ID>,...
# ・その他の失敗時は $?>1 で、標準出力には何も出力しない。(stderrに出る)
#
# [備考]
# ・在庫数が他の商品に依存しているような商品は、その依存先の商品の在庫
#   も合わせて減らす。例えばSHOCCAR2013がSHOCCAR8～SHOCCAR11に各1冊ずつ依
#   存している場合、SHOCCAR2013を1減らせばそれらも各1冊減る。
# ・成功すれば、商品IDの在庫数ファイルサイズを<要求数>だけ切り詰めて $?=0
# ・失敗した場合はエラーとして扱い、一切切り詰めない
#   - 在庫数(ファイルサイズ)が<要求数>を下回っている場合にはエラー($?=1)
#   - その他のエラーは$?>1
# ・全ての在庫を減らせなければ失敗(全ての商品の在庫数はそのまま)とする
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
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- エラー終了関数定義 ---------------------------------------------
error_exit() {
  [ -n "$2" ] && echo "${0##*/}: $2" 1>&2
  [ -f $Tmp-flockids ] && cat $Tmp-flockids | while read pid; do kill $pid;done
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
# 引数確認
######################################################################

# --- 引数の数は合っているか? ----------------------------------------
[ $# -gt 0 ] || error_exit 2 'No arguments, see the usage'

# --- 引数の書式は合っているか? --------------------------------------
for arg in "$@"; do echo "$arg"; done |
tee $Tmp-args                         |
grep -v '^[A-Za-z0-9_.-]\+:[0-9]\+$'  > /dev/null
# grepは出力するものが無いと $?!=0 になる。
# ここでは書式に当てはまらないものだけgrepで出力しようとしているので
# $?==0 の場合は不正ということになる。
[ $? -ne 0 ] || error_exit 3 'Invalid argument, see the usage'


######################################################################
# 要求商品ID一覧表を作る
######################################################################

# --- 商品マスターファイルの正規化&在庫依存情報の抽出 ----------------
[ -f "$File_PRODUCTS" ] || error_exit 4 'Product master file is not found'
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
self 1 6                              |
sort -k1,1                            > $Tmp-norm_products
# 1:商品ID 2:在庫依存情報 (正規化された状態)

# --- 要求数一覧表を作る ---------------------------------------------
cat $Tmp-args                                           |
tr ':' ' '                                              |
sort -k1,1                                              |
# 1:要求された商品ID 2:要求数                           #
tee $Tmp-takingreqs0                                    |
#join2 '+!' key=1 $Tmp-norm_products                     |
join -1 1 -2 1 -a 2 -o 2.1,1.2,2.2 $Tmp-norm_products - |
sed 's/  / ! /'                                         |
awk '$2!="*"'                                           | # 在庫無限(電子商品)等はerrにもせず無視
# 1:要求された商品ID 2:在庫依存情報 3:要求数            #
grep '!'                                                > $Tmp-unexistent_pid
# grepは出力するものが無いと $?>0 になる。
# ここでは商品マスターに存在しないはずの"!"という文字が含まれる行、
# つまり不正な行だけgrepで出力しようとしているので、1行も出力されてはいけない。
# にもかかわらず出力されてしまうと $?==0 となるので不正ということになる。
if [ $? -eq 0 ]; then
  nosuchpids=$(self 1 $Tmp-unexistent_pid |
               tr '\n' ','                |
               sed 's/,$//'               )
  error_exit 5 "No such product found ($nosuchpids)"
fi


######################################################################
# 要求商品IDから実際に在庫を持ち出される商品IDへの変換
######################################################################

# --- 在庫依存情報に基づき、商品IDと要求数を作り直す -----------------
cat $Tmp-takingreqs0                               |
sort -k1,1                                         |
# 1:商品ID 2:要求数 (正規化された状態)             #
#join1 key=1 $Tmp-norm_products                     |
join -1 1 -2 1 -o 2.1,1.2,2.2 $Tmp-norm_products - |
self 1 3 2                                         |
# 1:商品ID 2:要求数 3:在庫情報(カンマ区切り)       #
tr , ' '                                           | # 在庫情報はカンマ区切りなので
tarr num=2                                         | # カンマを外して
awk '$3=="@"{$3=$1} $3!="*"'                       | # 各行に展開する
# 1:商品ID(顧客が直接指定したもの) 2:要求数 3:商品ID(実質必要なもの)
self 3 2                                           |
# 1:商品ID(実質必要なもの) 2:要求数                #
sort -k1,1                                         | # 同じ商品IDのものを集約する
sm2 1 1 2 2                                        > $Tmp-takingreqs
# 1:商品ID(実質必要なもの)* 2:要求数


######################################################################
# 必要な在庫数ファイルをロックしつつ、在庫数が足りていることの確認
######################################################################

# --- 対象在庫数ファイル全てをロックする(ロックに失敗したらエラー終了)
: > $Tmp-flockids
for prodid in $(self 1 $Tmp-takingreqs); do
  File="$Dir_STOCK/$prodid"
  if [ \( ! -f "$File" \) -o \( ! -w "$File" \) ]; then
    error_exit 6 "The stockqty file for \"$prodid\" is not found or unwritable"
  fi
  exflock 5 "$File" >> $Tmp-flockids
  [ $? -eq 0 ] || error_exit 7 "Failed to lock the stockqty file ($File)"
done

# --- 現在庫数表を作る -----------------------------------------------
(cd "$Dir_STOCK"; ls -l) |
tail -n +2               |
self 9 5                 > $Tmp-stockqtys # 1:商品ID* 2:現在庫数

# --- 不足在庫一覧を求める -------------------------------------------
cat $Tmp-takingreqs                                             |
# 1:商品ID 2:要求数                                             #
sort -k1,1                                                      |
#join2 +0 key=1 $Tmp-stockqtys                                   |
join -1 1 -2 1 -a 2 -o 2.1,1.2,2.2 $Tmp-stockqtys -             |
sed 's/  / 0 /'                                                 |
# 1:商品ID 2:現在庫数 3:要求数                                  #
awk '$2<$3{printf(",%s(%d<%d)",$1,$2,$3);err=1} END{exit err;}' > $Tmp-notenoughs
if [ $? -ne 0 ]; then
  echo -n 'insufficient-stock: '
  cat $Tmp-notenoughs | sed '1s/^,//'
  error_exit 1 'Stock is not enough ('"$(cat $Tmp-notenoughs | sed '1s/^,//')"')'
fi


######################################################################
# 在庫を実際に減らす
######################################################################

# --- 在庫を減らす ---------------------------------------------------
cat $Tmp-takingreqs |
while read prodid quantity; do
  File="$Dir_STOCK/$prodid"
  truncate -s -$quantity "$File"
done

# --- 在庫数ファイルのロックを解除 -----------------------------------
cat $Tmp-flockids  |
while read pid; do
  kill $pid
done


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
