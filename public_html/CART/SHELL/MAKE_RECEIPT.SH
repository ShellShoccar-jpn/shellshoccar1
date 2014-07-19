#! /bin/sh

######################################################################
#
# MAKE_RECIET.SH
# レシートを作成する
# Written by Matsuura(richmikan@richlab.org) at 2013/10/16
#
# [引数] MAKE_RECIET.SH [-d 注文日] <カゴファイル>
# ・カゴファイルは次の仕様であること
#   - 商品ID カゴ入り数量 という行を0行以上含んでいること
# ・[注文日]は送料計算に利用される。
#   - 指定されれば、内部で呼び出している送料計算プログラム
#     "MAKE_POSTAGE_TABLE.SH"に渡す。
#
# [入力]
# ・上記カゴファイル
# ・商品マスターファイル($File_PRODUCTS)
#
# [出力]
# ・列構成…1:商品ID 2:商品名(mojihameエスケープ) 3:URL(無ければ"-")
#           4:単価(+税表記無) 5:注文数 6:小計
# ・最後から二つ手前の列に下記のような送料行
#   - 1:'TAX' 2:'消費税' 3:'-' 4:'-' 5:税別商品の合計税額
# ・最後から一つ手前の列に下記のような送料行
#   - 1:'POSTAGE' 2:'送料' 3:'-' 4:'-' 5:送料計
# ・最後の行に下記のような合計行
#   - 1:'TOTAL' 2:'合計' 3:'-' 4:'-' 5:合計額
# を返す
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
. $Homedir/CONFIG/TRADING.SHLIB # このお店の取り引きルール定義
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
# 引数確認
######################################################################

# --- 発送予定日オプションがあれば取得する ---------------------------
date_send_opt=''
if [ \( -n "_$1" \) -a \( "_$1" = '_-d' \)  ]; then
  shift
  if echo "_$1" | grep '^_[0-9]\{8,8\}$' >/dev/null; then
    date_send_opt="-d $1"
    shift
  else
    error_exit 2 'Invalid "-d" option'
  fi
fi

# --- 引数の数を確認 -------------------------------------------------
if [ $# -gt 1 ]; then
  error_exit 3 'Invalid argument'
fi

# --- 引数で指定された文字列が有効なファイルであることを確認 ---------
if [ $# -eq 0 ]; then
  file='-'
elif [ \( -f "$1" \) -o \( -c "$1" \) -o \( -p "$1" \) -o \( "_$1" = '_-' \) ]; then
  file=$1
else
  error_exit 4 'No such file found'
fi


######################################################################
# メイン
######################################################################

# --- 商品マスターファイルを正規化してコピー -------------------------
# 1)存在確認
[ -f "$File_PRODUCTS" ] || error_exit 5 'product mster file is not found'
# 2)正規化
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
sort -k1,1                            |
self 1/7                              > $Tmp-productmaster
# 1:商品ID 2:商品名(mojihameエンコード) 3:単価(+税表記含) 4:発売日 5:g重量 6:在庫情報体 7:URL

# --- 与えられたカゴファイルデータを正規化してコピー -----------------
if [ "_${file%.gz}" != "_$file" ]; then zcat "$file"; else cat "$file"; fi |
grep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+'                               |
sort                                                                       |
sm2 1 1 2 2                                                                > $Tmp-inthecart
# 1:商品ID 2:カゴ入り数量

# --- 小計を求め、レシートファイルに記入 -----------------------------
cat $Tmp-inthecart                                                            |
# 1:商品ID 2:カゴ入り数量                                                     #
#join1 key=1 $Tmp-productmaster                                                |
join -1 1 -2 1 -o 2.1,1.2,1.3,1.4,1.5,1.6,1.7,2.2 $Tmp-productmaster -        |
# 1:商品ID 2:商品名(mojihameエンコ) 3:単価(+税表記含) 4:発売日 5:重さ厚さ     #
# 6:在庫情報体 7:URL 8:カゴ入り数量                                           #
self 1 2 7 3 8                                                                |
# 1:商品ID 2:商品名(mojihameエンコード) 3:URL 4:単価(+税表記含) 5:カゴ入り数量
awk 'BEGIN        {sotozei_target_amt = 0;                          }         #
     $4~/\+[Tt]$/ {zeinuki_unitprice = substr($4,1,length($4)-2);             #
                   sotozei_target_amt += zeinuki_unitprice*$5;                #
                   print $1,$2,$3,zeinuki_unitprice,$5,zeinuki_unitprice*$5;} #
     $4~/^[0-9]+$/{print $0,$4*$5;                                  }         #
     END          {tax = int(sotozei_target_amt*'"$TR_TAX_RATE"');            #
                   print "TAX 消費税(税別商品分) -", tax, 1, tax;}'           > $Tmp-reciept
# 1:商品ID 2:商品名(mojihameエンコード) 3:URL 4:単価(税抜) 5:カゴ入り数量 6:小計

# --- 送料を求め、レシートファイルに追記する -------------------------
postage=$($Homedir/SHELL/MAKE_POSTAGE_TABLE.SH $date_send_opt $Tmp-inthecart |
          tail -n 1                                                          |
          self 2                                                             |
          tr -d ,                                                            )
postage_desc=''
total_desc=''
if [ "_$postage" = "_-1" ]; then
  postage=0;
  postage_desc='(別途お見積)'
  total_desc='(送料除く)'
fi
echo "POSTAGE 送料$postage_desc - $postage 1 $postage"  >> $Tmp-reciept

# --- 総合計を求め、レシートファイルに追記する -----------------------
totalprice=$(sm2 0 0 6 6 $Tmp-reciept)
echo "TOTAL 合計$total_desc - $totalprice 1 $totalprice" >> $Tmp-reciept

# --- 出力する -------------------------------------------------------
cat $Tmp-reciept


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
