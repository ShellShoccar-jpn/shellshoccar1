#! /bin/sh

#####################################################################
#
# MAKE_ZIPDIC_KENALL_BATCH.SH
# 日本郵便公式の郵便番号住所CSVから、本システム用の辞書を作成（地域名）
# Written by Matsuura(richmikan@richlab.org) at 2014/01/18
#
# Usage : MAKE_ZIPDIC_KENALL_BATCH.SH -f
#         -f ... ・サイトにあるCSVファイルのタイプスタンプが、
#                  今ある辞書ファイルより新しくても更新する
#
# [出力]
# ・戻り値
#   - 作成成功もしくはサイトのタイムスタンプが古いために作成する必要無
#     しの場合は0、失敗したら0以外
# ・成功時には辞書ファイルを更新する。
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
. $Homedir/CONFIG/ZIPCODE.SHLIB # 郵便番号辞書関連定義
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

# --- 引数チェック ---------------------------------------------------
force=0
[ \( $# -gt 0 \) -a \( "_$1" = '_-f' \) ] && force=1

# --- サイト上のファイルのタイムスタンプを取得 -----------------------
timestamp_web=$(curl -sLI $URL_ZIPCSVZIP_KENALL                              |
                awk '                                                        #
                  BEGIN{                                                     #
                    status = 0;                                              #
                    d["Jan"]="01";d["Feb"]="02";d["Mar"]="03";d["Apr"]="04"; #
                    d["May"]="05";d["Jun"]="06";d["Jul"]="07";d["Aug"]="08"; #
                    d["Sep"]="09";d["Oct"]="10";d["Nov"]="11";d["Dec"]="12"; #
                  }                                                          #
                  /^HTTP\// { status = $2; }                                 #
                  /^Last-Modified/ {                                         #
                    gsub(/:/, "", $6);                                       #
                    ts = sprintf("%04d%02d%02d%06d" ,$5,d[$4],$3,$6);        #
                  }                                                          #
                  END {                                                      #
                    if ((status>=200) && (status<300) && (length(ts)==14)) { #
                      print ts;                                              #
                    } else {                                                 #
                      print "NOT_FOUND";                                     #
                    }                                                        #
                  }'                                                         )
[ "$timestamp_web" != 'NOT_FOUND' ] || error_exit 10 'The zipcode CSV file not found on the web'
echo "_$timestamp_web" | sed '1s/_//' | grep '^[0-9]\{14\}$' >/dev/null
[ $? -eq 0 ] || timestamp_web=$(TZ=UTC/0 date +%Y%m%d%H%M%S) # 取得できなければ現在日時を入れる

# --- 手元の辞書ファイルのタイムスタンプと比較し、更新必要性確認 -----
while [ $force -eq 0 ]; do
  # 手元に辞書ファイルはあるか?
  [ ! -f "$File_ZIPDIC_KENALL" ] && break
  # その辞書ファイル内にタイムスタンプは記載されているか?
  timestamp_local=$(head -n 1 "$File_ZIPDIC_KENALL" | awk '{print $NF}')
  echo "_$timestamp_local" | sed '1s/_//' | grep '^[0-9]\{14\}$' >/dev/null
  [ $? -eq 0 ] || break
  # サイト上のファイルは手元のファイルよりも新しいか?
  [ $timestamp_web -gt $timestamp_local ] && break
  # そうでなければ何もせず終了
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
done

# --- 郵便番号CSVデータファイル(Zip形式)ダウンロード -----------------
curl -s $URL_ZIPCSVZIP_KENALL > $Tmp-zip
ret=$?
[ $ret -eq 0 ] || error_exit $ret 'Failed to download the zipcode CSV file'

# --- 郵便番号辞書ファイル作成 ---------------------------------------
unzip -p $Tmp-zip                                                 |
# 日本郵便 郵便番号-住所 CSVデータ(Shift_JIS)                     #
if   which iconv >/dev/null; then                                 #
  iconv -c -f SHIFT_JIS -t UTF-8                                  #
elif which nkf   >/dev/null; then                                 #
  nkf -Sw80                                                       #
else                                                              #
  error_exit 6 'No KANJI convertors found (iconv or nkf)'         #
fi                                                                |
# 日本郵便 郵便番号-住所 CSVデータ(UTF-8変換済)                   #
parsrc.sh                                                         |
# 1:行番号 2:列番号 3:CSVデータセルデータ                         #
awk '$2~/^3|7|8|9$/'                                              |
# 1:行番号 2:列番号(3=郵便番号,7=都道府県,8=市区町村,9=町) 3:データ
awk 'BEGIN{z="#"; p="generated"; c="at"; t="'$timestamp_web'"; }  #
     $1!=line      {pl();z="";p="";c="";t="";line=$1;          }  #
     $2==3         {z=$3;                                      }  #
     $2==7         {p=$3;                                      }  #
     $2==8         {c=$3;                                      }  #
     $2==9         {t=$3;                                      }  #
     END           {pl();                                      }  #
     function pl() {print z,p,c,t;                             }' |
sed 's/（.*//'                                                    | # 地域名住所文字列で小括弧以降は使えないので除去する
sed 's/以下に.*//'                                                > $Tmp-zipdic # 「以下に」の場合も同様
# 1:郵便番号 2:都道府県名 3:市区町村名 4:町名
[ -s $Tmp-zipdic ] || error_exit 11 'Failed to make the zipcode dictionary file'
mv $Tmp-zipdic "$File_ZIPDIC_KENALL"
[ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$File_ZIPDIC_KENALL"


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
