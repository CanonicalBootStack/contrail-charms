#!/bin/bash
# Copyright (C) 2011, 2014, 2020 Canonical
# All Rights Reserved
# Author: Liam Young, Jacek Nykis, Peter Sabaini

# Produce a queue data for a given vhost. Useful for graphing and Nagios checks
LOCK=/var/lock/rabbitmq-gather-metrics.lock
# Check for a lock file and if not, create one
lockfile-create -r2 --lock-name $LOCK > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Failed to create lockfile: $LOCK."
    exit 1
fi
trap "rm -f $LOCK > /dev/null 2>&1" exit

# Required to fix the bug about start-stop-daemon not being found in
# rabbitmq-server 2.7.1-0ubuntu4.
# '/usr/sbin/rabbitmqctl: 33: /usr/sbin/rabbitmqctl: start-stop-daemon: not found'
export PATH=${PATH}:/sbin/

RABBIT_CONTAINER=$( docker ps |awk '/rabbitmq/{ print $10 }' )

DATA_DIR="/var/lib/misc/rabbitmq-check"
DATA_FILE="${DATA_DIR}/rabbitmq_queue_stats.dat"
LOG_DIR="$DATA_DIR/logs"
RABBIT_STATS_DATA_FILE="${DATA_DIR}/rabbitmq_general_stats.dat"
NOW=$(date +'%s')
HOSTNAME=$(hostname -s)

rabbit_docker() {
  docker exec $RABBIT_CONTAINER bash -c "$@"
}

MNESIA_DB_SIZE=$( rabbit_docker 'du -sm /var/lib/rabbitmq/mnesia | cut -f1' )
RABBIT_RSS=$( rabbit_docker 'ps -p $( pgrep -f "[b]eam.*rabbit") -o rss=' )

mkdir -p $DATA_DIR $LOG_DIR

TMP_DATA_FILE=$(mktemp -p ${DATA_DIR})
echo "#Vhost Name Messages_ready Messages_unacknowledged Messages Consumers Memory Time" > ${TMP_DATA_FILE}
rabbit_docker '/opt/rabbitmq/sbin/rabbitmqctl -q --no-table-headers list_vhosts' | \
while read VHOST; do
    rabbit_docker "/opt/rabbitmq/sbin/rabbitmqctl -q --no-table-headers list_queues -p $VHOST name messages_ready messages_unacknowledged messages consumers memory" | \
    awk "{print \"$VHOST \" \$0 \" $(date +'%s') \"}" >> ${TMP_DATA_FILE} 2>${LOG_DIR}/list_queues.log
done
mv ${TMP_DATA_FILE} ${DATA_FILE}
chmod 644 ${DATA_FILE}
echo "mnesia_size: ${MNESIA_DB_SIZE}@$NOW" > $RABBIT_STATS_DATA_FILE
echo "rss_size: ${RABBIT_RSS}@$NOW" >> $RABBIT_STATS_DATA_FILE
