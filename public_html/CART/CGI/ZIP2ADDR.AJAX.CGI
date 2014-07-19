#! /bin/sh

######################################################################
#
# ZIP2ADDR.AJAX.CGI
# 郵便番号―住所検索
# Written by Matsuura(richmikan@richlab.org) at 2014/01/18
#
# [入力]
# ・[CGI変数]
#   - zipcode: 7桁の郵便番号(ハイフン無し)
# [出力]
# ・成功すればJSON形式で郵便番号、都道府県名、市区町村名、町名
# ・郵便番号辞書ファイル無し→500エラー
# ・郵便番号指定が不正      →400エラー
# ・郵便番号が見つからない  →空文字のJSONを返す
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB  
. $Homedir/CONFIG/ZIPCODE.SHLIB # 郵便番号辞書関連定義
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- エラー終了関数定義 ---------------------------------------------
errorcode_exit() {
  cat <<-__HTTP_HEADER
	Status: 500 Internal Server Error
	Content-Type: text/plain

	500 Internal Server Error
	($@)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
}
dyingmessage() {
  printf 'Content-Type: text/plain\n\n'
  echo "$@"
  exit
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -z "$DISABLE_SHLOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/CGI
  ([ "$SUEXEC_MODE" -eq 0 ] && umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || errorcode_exit 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# メイン
######################################################################

# --- 郵便番号データファイルはあるか？ -------------------------------
[ -f "$File_ZIPDIC_KENALL"   ] || errorcode_exit 'zipcode dictionary file (ken_all) not found'
[ -f "$File_ZIPDIC_JIGYOSYO" ] || errorcode_exit 'zipcode dictionary file (jigyosyo) not found'

# --- CGI変数(GETメソッド)で指定された郵便番号を取得 -----------------
printf '%s' "${QUERY_STRING:-}" |
cgi-name                        |
nameread zipcode                |
grep '^[0-9]\{7\}$'             |
tr -d '\n'                      > $Tmp-zipcode
if [ ! -s $Tmp-zipcode ]; then
  cat <<-__HTTP_HEADER
	Status: 400 Bad Request
	Content-Type: text/plain

	400 Bad Request
	(invalid zipcode)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
fi

# --- JSON形式文字列を生成して返す -----------------------------------
cat "$File_ZIPDIC_KENALL" "$File_ZIPDIC_JIGYOSYO"                             |
awk '$1=="'$(cat $Tmp-zipcode)'"{hit=1;print;exit} END{if(hit==0){print ""}}' |
while read zip pref city town; do
  cat <<-__HTTP_RESPONSE
	Content-Type: application/json; charset=utf-8
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

	{"zip":"$zip","pref":"$pref","city":"$city","town":"$town"}
__HTTP_RESPONSE
  break
done

# --- 正常終了 -------------------------------------------------------
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
