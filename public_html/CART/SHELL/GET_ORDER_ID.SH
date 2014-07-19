#! /bin/sh

######################################################################
#
# GET_ORDER_ID.SH
# 一意な注文番号IDを発行する
# Written by Matsuura(richmikan@richlab.org) at 2014/01/14
#
# [引数] GET_STOCKQTYS.SH [プレフィックス]["*"による桁数]
# ・引数の書式
#   - プレフィックスは、[A-Za-z0-9._-]* (省略可)
#   - "*"による桁数は、\*+（これも省略可）
#   - 上記に基づく例1 "SH00000"…"SH"+5桁で注文番号IDを発行(SH00128等)
#   - 上記に基づく例2 "0000000"…7桁で数字のみの注文番号IDを発行(0001024等)
#   - 上記に基づく例3 "" …………必要に応じた桁数で数字のみの注文IDを発行(32等)
# ・引数の意味は「出力」を参照
#
# [その他入力]
# ・注文番号IDファイル(「出力」参照)
#
# [出力]
# ・標準出力に次の文字列を返す。
#     PPPnnn
#   - PPPは、プレフィックスで指定した文字列（英数と".","_","-"、長さ自由）
#   - nnnは、桁数で指定した数だけ0パディングした状態の一意なID番号。
#     ID番号の値は、$Dir_ORDERID/<プレフィックス> で指定したファイルの
#     現在のサイズ+1となる。ファイルが無ければ作ろうとする
#   - プレフィックスが空文字だった場合はファイル名は"(noprefix)"と見なす。
# ・戻り値は、成功なら0。失敗ならそれ以外。
#
# [注意]
# ・注文番号IDファイルは、CGIから書き込めるようにしておくこと。
# ・$Dir_ORDERIDディレクトリーのCGIに対するパーミッションをr-xにしても
#   よいが、その場合は新規作成ができないので、CGIにとってrw-なファイル
#   を作っておくこと。
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
. $Homedir/CONFIG/TRADING.SHLIB # 郵便番号辞書関連定義
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
# メイン
######################################################################

# --- 引数の数は合っているか? ----------------------------------------
[ $# -eq 1 ] || error_exit 2 'Too few or many arguments, see the usage'

# --- 引数の書式は合っているか? --------------------------------------
s=$(printf '%s' "$1" | sed 's/\**$//')
digits=$((${#1}-${#s}))
prefix=''
if [ -n "$s" ]; then
  printf '%s' "$s" | grep '^[A-Za-z0-9._-]*$' >/dev/null
  [ $? -eq 0                         ] || error_exit 3 'Invalid prefix'
  printf '%s' "$s" | grep '^\.\.\?$' >/dev/null
  [ $? -ne 0                         ] || error_exit 4 'Unavailable prefix'
  prefix=$s
fi

# --- プレフィックスで指定されたファイルのサイズを+1し、注文番号を発行
if [ -n "$prefix" ]; then
  File_ORDERNUM="$Dir_ORDERID/$prefix"
else
  File_ORDERNUM="$Dir_ORDERID/(noprefix)"
fi
[ -z "$prefix"                       ] && File_ORDERNUM="$Dir_ORDERID/(noprefix)"
[ -f "$File_ORDERNUM"                ] || touch "$File_ORDERNUM"
[ $? -eq 0                           ] || error_exit 5 "Can't create the order number file for \"$prefix\""
exflock 10 "$File_ORDERNUM" >/dev/null || error_exit 6 "Failed to lock the order number file for \"$prefix\""
printf 1 >> "$File_ORDERNUM"           || error_exit 7 "Failed to write into the order number file for \"$prefix\""
[ "$SUEXEC_MODE" -eq 0               ] && chmod go+rw "$File_ORDERNUM"
cur_order_num=$(ls -l "$File_ORDERNUM" | self 5)

# --- 書式に基づいて注文番号IDを出力する -----------------------------
printf "%s%0${digits}d\n" "$prefix" $cur_order_num


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
