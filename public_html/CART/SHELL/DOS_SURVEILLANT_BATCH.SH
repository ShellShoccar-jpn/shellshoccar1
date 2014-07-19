#! /bin/sh

######################################################################
#
# DOS_SURVEILLANT_BATCH.SH
# DoS攻撃の監視者
# Written by Matsuura(richmikan@richlab.org) at 2013/10/30
#
# [概要]
# (a)異常なサイズの/tmpファイルやログファイルの削除
# (b)ディスク空き容量が一定閾値を下回った場合の警告メール送信
#
# [引数]なし
#
# [出力]
# ・(a)についてはstderrに出力され、cronからのメールになる
# ・(b)については管理者へ直接メールが飛ぶ
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
. $Homedir/CONFIG/DOSSURV.SHLIB # このスクリプト用の設定
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
# 異常なサイズのファイル検出&原因プロセスkill
######################################################################

# --- 異常サイズのログの生成プロセスkill -----------------------------
find $Homedir/LOG/ -type f -size +${DS_EXTRAORDINARY_LOGFILE_SIZE}c |
while read File; do
  pid=(echo "$File" | sed 's/^.\{1,\}\.\([0-9]\{1,\}\)\.log$/\1/')
  [ $pid -gt 1 ] || continue
  kill -s TERM -$pid /dev/null 2>&1
  echo "${0##*/}: The file \"$File\" is extraordinary size. The process makes this file has killed." 1>&2
done

# --- 異常サイズの/tmpファイル及び生成プロセスkill -------------------
find /tmp -type f -size +${DS_EXTRAORDINARY_TMPFILE_SIZE}c |
grep '^/tmp/[A-Z0-9_.-]\+-[0-9]\+-[A-Za-z0-9_.-]\+$'       |
while read File; do
  pid=(echo "$File" | sed 's!^/tmp/[A-Z0-9_.-]\{1,\}-\([0-9]\{1,\}\)-[A-Za-z0-9_.-]\{1,\}$!\1!')
  [ $pid -gt 1 ] || continue
  kill -s TERM -$pid /dev/null 2>&1
  rm -f $File
  echo "${0##*/}: The file \"$File\" is extraordinary size. The file and the process makes this file has killed." 1>&2
done


######################################################################
# 異常なサイズのファイル検出&原因プロセスkill
######################################################################

# --- 
use=$(env - df | awk '$6~/^'"$DS_MOUNT_POINTS_REGEX"'$/{sub(/%/,"",$5);print $5}')

# --- 
if [ \( ! -f "$Homedir/CONFIG/DS_ALERT_DF" \) -a \( -n "$use" \) -a \( "$use" -ge "$DS_WARNING_PERCENT" \) ]; then
  touch "$Homedir/CONFIG/DS_ALERT_DF"
  echo "$DS_ALERTMAIL_BODY"   |
  sed 's/###USE###/$use/g'    > $Tmp-alertmail
  sendjpmail $Tmp-alertmail $Tmp-email
  [ $? -eq 0 ] || echo "${0##*/}: FAILED TO SEND AN ALERT MAIL!!!"
fi

# --- 
if [ \( -z "$DISABLE_SHLOG" \) -a \( -n "$use" \) -a \( "$use" -ge "$DS_WARNING_PERCENT" \) ]; then
  printf '\nDISABLE_SHLOG=1\n' >> $Homedir/CONFIG/COMMON.SHLIB
fi

######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
