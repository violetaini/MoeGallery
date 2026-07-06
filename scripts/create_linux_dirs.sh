#!/usr/bin/env bash
set -euo pipefail

install -d -o www-data -g www-data /opt/anime-gallery/storage/original
install -d -o www-data -g www-data /opt/anime-gallery/storage/preview
install -d -o www-data -g www-data /opt/anime-gallery/storage/thumbnail
install -d -o www-data -g www-data /opt/anime-gallery/storage/tasks
install -d -o www-data -g www-data /opt/anime-gallery/logs
chown -R www-data:www-data /opt/anime-gallery/storage /opt/anime-gallery/logs
