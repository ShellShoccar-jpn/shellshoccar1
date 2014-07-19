#! /bin/sh

######################################################################
#
# CANCEL_ORDER.SH
# 注文をキャンセル処理する
# Written by Matsuura(richmikan@richlab.org) at 2013/10/28
#
# [引数] CANCEL_ORDER.SH <注文票ファイル> [注文票ファイル...]
# ・引数で与えられた注文票ファイルをキャンセル処理し、
#   $Dir_ORDER/{ON,OFF}LINE.3_CANCELLED に移動する。
# ・その際、在庫数を元に戻す。
#
# [出力]
# ・戻り値
#   - 全て成功すれば0、失敗した場合は、失敗した数を返す(最大255)
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
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit $1
}

# --- 終了関数定義 ---------------------------------------------------
exit_trap() {
  trap 0 1 2 3 12 14 15
  cat $Tmp-cancelled_pids | self 2 | while read line; do kill $line; done
  [ -n "$Tmp" ] && rm -f $Tmp*
  [ $num_of_failure -gt 255 ] && num_of_failure=255
  exit $num_of_failure
}
touch $Tmp-cancelled_pids
num_of_failure=0
trap "exit_trap; exit" 0 1 2 3 12 14 15

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

# --- キャンセル注文票ファイルの移動先ディレクトリーの確保 -----------
Dir_off_cancel="$Dir_ORDER/OFFLINE.3_CANCELLED"
if [ ! -d "$Dir_off_cancel" ]; then
  mkdir -p "$Dir_off_cancel"
  if [ ! -d "$Dir_off_cancel" ]; then
    echo "${0##*/}: The directory for order cancel (offline) is not available" 1>&2
    num_of_failure=$#
    exit_trap
  fi
fi
Dir_on_cancel="$Dir_ORDER/ONLINE.3_CANCELLED"
if [ ! -d "$Dir_on_cancel" ]; then
  mkdir -p "$Dir_on_cancel"
  if [ ! -d "$Dir_on_cancel" ]; then
    echo "${0##*/}: The directory for order cancel (online) is not available" 1>&2
    num_of_failure=$#
    exit_trap
  fi
fi

# --- 商品ファイルの正規化をしておく ---------------------------------
[ -f "$File_PRODUCTS" ] || { num_of_failure=$#; exit_trap; }
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
self 1 6                              |
sort -k1,1                            > $Tmp-norm_products
# 1:商品ID 2:在庫依存情報 (正規化された状態)

# === 引数ごとにループ ===============================================
for file in "$@"; do

  # --- そもそもファイルが無ければエラー -----------------------------
  if [ ! -f "$file" ]; then
    echo "${0##*/}: No such file found ($file)" 1>&2
    num_of_failure=$((num_of_failure+1))
    continue
  fi

  # --- 正しい注文商品が全く入っていなければエラー -------------------
  if [ "_${file%.gz}" != "_$file" ]; then zcat "$file"; else cat "$file"; fi        |
  grep '^ordered[[:blank:]]\+[A-Za-z0-9_.-]\+[[:blank:]]\+.\+[[:blank:]]\+[0-9]\+$' |
  self 2 NF                                                                         |
  awk '$2>0'                                                                        |
  sort -k1,1                                                                        |
  #  1:カゴ入り商品ID 2:カゴ入り数                                                  #
  #join1 key=1 $Tmp-norm_products                                                    |
  join -1 1 -2 1 -o 2.1,1.2,1.3 $Tmp-norm_products -                                |
  self 1 3 2                                                                        |
  # 1:商品ID 2:要求数 3:在庫情報(カンマ区切り)                                      #
  tr , ' '                                                                          | # 在庫情報はカンマ区切りなので
  tarr num=2                                                                        | # カンマを外して
  awk '$3=="@"{$3=$1} $3!="*"'                                                      | # 各行に展開する
  # 1:商品ID(顧客が直接指定したもの) 2:要求数 3:商品ID(実質必要なもの)              #
  self 3 2                                                                          |
  # 1:商品ID(実質必要なもの) 2:要求数                                               #
  sort -k1,1                                                                        | # 同じ商品IDのものを集約する
  sm2 1 1 2 2                                                                       > $Tmp-calcel_pidqtys
  if [ $(gyo $Tmp-calcel_pidqtys) -eq 0 ]; then
    echo "${0##*/}: Invalid order file ($file)" 1>&2
    num_of_failure=$((num_of_failure+1))
    continue
  fi

  # --- 商品在庫を元に戻す -------------------------------------------
  exec 9<&0 < $Tmp-calcel_pidqtys
  i=0; j=0
  while read pidqty; do
    i=$((i+1))
    pid=${pidqty% *}
    qty=${pidqty#* }
    grep "^$pid[[:blank:]]" $Tmp-cancelled_pids > /dev/null
    if [ $? -ne 0 ]; then
      exflock 5 "$Dir_STOCK/$pid" > $Tmp-flockid
      if [ $? -ne 0 ]; then
        echo "${0##*/}: Fail to lock for pid:$pid" 1>&2
        j=$((j+1))
        continue
      fi
      echo "$pid $(cat $Tmp-flockid)" >> $Tmp-cancelled_pids
    fi
    printf "%0${qty}d" 0 >> $Dir_STOCK/$pid
  done
  exec 0<&9 9<&-
  if [ $j -gt 0 ]; then
    echo "${0##*/}: $j/$i product(s) in the file ($file) was failed to cancel" 1>&2
    num_of_failure=$((num_of_failure+1))
    [ $j -lt $i ] || continue
  fi

  # --- 注文票ファイルをキャンセルディレクトリーに移動 ---------------
  s=$(d=${file%/*}/; [ "_$d" = "_$file/" ] && d='./'; cd "$d"; pwd)
  if   [ "_${s##*/}" = '_ONLINE.1_ORDERED'  ]; then
    mv -f $file "$Dir_on_cancel"
  elif [ "_${s##*/}" = '_OFFLINE.1_ORDERED' ]; then
    mv -f $file "$Dir_off_cancel"
  else
    echo "${0##*/}: Cannot distinguish whether online or offline" 1>&2
    num_of_failure=$((num_of_failure+1))
    continue
  fi
  if [ $? -ne 0 ]; then
    echo "${0##*/}: Fail to move the file ($file) to the cancel directory" 1>&2
    num_of_failure=$((num_of_failure+1))
    continue
  fi

done
# === 引数ごとにループ ここまで ======================================


######################################################################
# 終了
######################################################################

exit_trap
