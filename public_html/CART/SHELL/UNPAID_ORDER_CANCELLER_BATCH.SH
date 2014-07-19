#! /bin/sh

#####################################################################
#
# UNPAID_ORDER_CANCELLER.SH
# 未払いで放置されたオンライン注文票を整理する
# Written by Matsuura(richmikan@richlab.org) at 2013/10/28
#
# [動作]
# ・$TR_LIFETIME_MIN_NOT_PAID_ONLINE分以上経過しても決済されていないオ
#   ンライン注文票ファイル($Dir_ORDER/ONLINE.1_ORDEREDの中)を集め、キャ
#   ンセル処理(CANCEL_ORDER.SH呼び出し)する。
#
# [引数]
# ・なし
#
# [出力]
# ・戻り値
#   - ログファイル生成失敗時に1を返す
#   - それ以外は整理に失敗しても0を返す(真の結果はログを参照のこと)
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
. $Homedir/CONFIG/TRADING.SHLIB # 取引ルール定義
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

# --- TR_LIFETIME_MIN_NOT_PAID_ONLINE分以上経過した古い注文票ファイルを処理する
find "$Dir_ORDER/ONLINE.1_ORDERED" -type f -mmin +$TR_LIFETIME_MIN_NOT_PAID_ONLINE |
xargs $Homedir/SHELL/CANCEL_ORDER.SH

# --- 正常終了 -------------------------------------------------------
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
