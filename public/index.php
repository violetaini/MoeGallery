<?php
session_start();

define('DATA_PATH', dirname(__DIR__) . '/data');

define('UPLOAD_PATH', __DIR__ . '/uploads');

define('UPLOAD_URL', '/uploads');

function load_data(string $file, array $fallback = []): array {
    $path = DATA_PATH . '/' . $file;
    if (!file_exists($path)) {
        return $fallback;
    }
    $contents = file_get_contents($path);
    $decoded = json_decode($contents, true);
    return is_array($decoded) ? $decoded : $fallback;
}

function save_data(string $file, array $data): void {
    $path = DATA_PATH . '/' . $file;
    file_put_contents($path, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

function current_user(): ?array {
    return $_SESSION['user'] ?? null;
}

function require_login(): void {
    if (!current_user()) {
        header('Location: ?page=login');
        exit();
    }
}

function require_admin(): void {
    $user = current_user();
    if (!$user || $user['role'] !== 'admin') {
        http_response_code(403);
        echo '<h1>403 - 权限不足</h1>';
        exit();
    }
}

function find_by_id(array $items, string $id): ?array {
    foreach ($items as $item) {
        if ($item['id'] === $id) {
            return $item;
        }
    }
    return null;
}

function update_item(array $items, string $id, array $payload): array {
    return array_map(function ($item) use ($id, $payload) {
        if ($item['id'] === $id) {
            return array_merge($item, $payload);
        }
        return $item;
    }, $items);
}

function delete_item(array $items, string $id): array {
    return array_values(array_filter($items, fn($item) => $item['id'] !== $id));
}

function handle_upload(string $field): string {
    if (!isset($_FILES[$field]) || $_FILES[$field]['error'] !== UPLOAD_ERR_OK) {
        return '';
    }
    if (!is_dir(UPLOAD_PATH)) {
        mkdir(UPLOAD_PATH, 0775, true);
    }
    $ext = pathinfo($_FILES[$field]['name'], PATHINFO_EXTENSION);
    $name = uniqid('img_', true) . ($ext ? '.' . $ext : '');
    $target = UPLOAD_PATH . '/' . $name;
    if (!move_uploaded_file($_FILES[$field]['tmp_name'], $target)) {
        return '';
    }
    return UPLOAD_URL . '/' . $name;
}

function handle_multi_upload(string $field): array {
    if (!isset($_FILES[$field]) || !is_array($_FILES[$field]['name'])) {
        return [];
    }
    $paths = [];
    foreach ($_FILES[$field]['name'] as $index => $name) {
        if ($_FILES[$field]['error'][$index] !== UPLOAD_ERR_OK) {
            continue;
        }
        $ext = pathinfo($name, PATHINFO_EXTENSION);
        if (!is_dir(UPLOAD_PATH)) {
            mkdir(UPLOAD_PATH, 0775, true);
        }
        $filename = uniqid('img_', true) . ($ext ? '.' . $ext : '');
        $target = UPLOAD_PATH . '/' . $filename;
        if (move_uploaded_file($_FILES[$field]['tmp_name'][$index], $target)) {
            $paths[] = UPLOAD_URL . '/' . $filename;
        }
    }
    return $paths;
}

$settings = load_data('settings.json', []);
$works = load_data('works.json', []);
$characters = load_data('characters.json', []);
$images = load_data('images.json', []);
$users = load_data('users.json', []);
$shares = load_data('shares.json', []);

$page = $_GET['page'] ?? 'gallery';

if (!in_array($page, ['login', 'logout', 'share'], true)) {
    require_login();
}

$errors = [];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';
    if ($action === 'login') {
        $username = trim($_POST['username'] ?? '');
        $password = $_POST['password'] ?? '';
        foreach ($users as $user) {
            if ($user['username'] === $username && password_verify($password, $user['password_hash'])) {
                $_SESSION['user'] = $user;
                header('Location: ?page=gallery');
                exit();
            }
        }
        $errors[] = '账号或密码错误。';
    }

    if ($action === 'logout') {
        session_destroy();
        header('Location: ?page=login');
        exit();
    }

    if ($action === 'add_work') {
        require_admin();
        $poster = handle_upload('poster');
        if (!$poster) {
            $errors[] = '请上传作品海报。';
        } else {
            $works[] = [
                'id' => uniqid('w_'),
                'name' => trim($_POST['name'] ?? ''),
                'alias' => trim($_POST['alias'] ?? ''),
                'description' => trim($_POST['description'] ?? ''),
                'poster' => $poster
            ];
            save_data('works.json', $works);
            header('Location: ?page=works');
            exit();
        }
    }

    if ($action === 'update_work') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $poster = handle_upload('poster');
        $currentWork = find_by_id($works, $id);
        $works = update_item($works, $id, [
            'name' => trim($_POST['name'] ?? ''),
            'alias' => trim($_POST['alias'] ?? ''),
            'description' => trim($_POST['description'] ?? ''),
            'poster' => $poster ?: ($currentWork['poster'] ?? '')
        ]);
        save_data('works.json', $works);
        header('Location: ?page=works');
        exit();
    }

    if ($action === 'delete_work') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $works = delete_item($works, $id);
        $characters = array_values(array_filter($characters, fn($c) => $c['work_id'] !== $id));
        $images = array_values(array_filter($images, fn($i) => $i['work_id'] !== $id));
        save_data('works.json', $works);
        save_data('characters.json', $characters);
        save_data('images.json', $images);
        header('Location: ?page=works');
        exit();
    }

    if ($action === 'add_character') {
        require_admin();
        $workId = $_POST['work_id'] ?? '';
        $avatar = handle_upload('avatar');
        if (!$avatar) {
            $errors[] = '请上传角色头像。';
        } else {
            $characters[] = [
                'id' => uniqid('c_'),
                'work_id' => $workId,
                'name' => trim($_POST['name'] ?? ''),
                'avatar' => $avatar
            ];
            save_data('characters.json', $characters);
            header('Location: ?page=work&id=' . urlencode($workId));
            exit();
        }
    }

    if ($action === 'update_character') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $workId = $_POST['work_id'] ?? '';
        $avatar = handle_upload('avatar');
        $currentCharacter = find_by_id($characters, $id);
        $characters = update_item($characters, $id, [
            'name' => trim($_POST['name'] ?? ''),
            'avatar' => $avatar ?: ($currentCharacter['avatar'] ?? '')
        ]);
        save_data('characters.json', $characters);
        header('Location: ?page=work&id=' . urlencode($workId));
        exit();
    }

    if ($action === 'delete_character') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $workId = $_POST['work_id'] ?? '';
        $characters = delete_item($characters, $id);
        $images = array_values(array_filter($images, fn($i) => $i['character_id'] !== $id));
        save_data('characters.json', $characters);
        save_data('images.json', $images);
        header('Location: ?page=work&id=' . urlencode($workId));
        exit();
    }

    if ($action === 'add_image') {
        require_admin();
        $characterId = $_POST['character_id'] ?? '';
        $workId = $_POST['work_id'] ?? '';
        if (!$workId && $characterId) {
            $character = find_by_id($characters, $characterId);
            $workId = $character['work_id'] ?? '';
        }
        $uploads = handle_multi_upload('image_files');
        if (!$uploads) {
            $errors[] = '请上传图片文件。';
        } else {
            foreach ($uploads as $upload) {
                $images[] = [
                    'id' => uniqid('i_'),
                    'work_id' => $workId,
                    'character_id' => $characterId,
                    'path' => $upload
                ];
            }
            save_data('images.json', $images);
            header('Location: ?page=character&id=' . urlencode($characterId));
            exit();
        }
    }

    if ($action === 'delete_image') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $characterId = $_POST['character_id'] ?? '';
        $redirect = $_POST['redirect'] ?? '';
        $images = delete_item($images, $id);
        save_data('images.json', $images);
        if ($redirect) {
            header('Location: ' . $redirect);
        } else {
            header('Location: ?page=character&id=' . urlencode($characterId));
        }
        exit();
    }

    if ($action === 'update_image') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $characterId = $_POST['character_id'] ?? '';
        $upload = handle_upload('image_file');
        if (!$upload) {
            $errors[] = '请上传新的图片文件。';
        } else {
            $images = update_item($images, $id, [
                'path' => $upload
            ]);
            save_data('images.json', $images);
            header('Location: ?page=image&id=' . urlencode($id));
            exit();
        }
    }

    if ($action === 'update_settings') {
        require_admin();
        $settings['site_name'] = trim($_POST['site_name'] ?? '');
        $settings['copyright'] = trim($_POST['copyright'] ?? '');
        $settings['login_backgrounds']['mode'] = $_POST['bg_mode'] ?? 'random';
        if (!empty($_POST['favicon_clear'])) {
            $settings['favicon'] = '';
        }
        $faviconUpload = handle_upload('favicon_file');
        if ($faviconUpload) {
            $settings['favicon'] = $faviconUpload;
        }
        if (!empty($_POST['reset_bg'])) {
            $settings['login_backgrounds']['images'] = [];
        }
        $newBackgrounds = handle_multi_upload('bg_images');
        if ($newBackgrounds) {
            $settings['login_backgrounds']['images'] = array_values(array_merge($settings['login_backgrounds']['images'] ?? [], $newBackgrounds));
        }
        $settings['gallery_preferences']['character_ids'] = $_POST['preference_ids'] ?? [];
        save_data('settings.json', $settings);
        header('Location: ?page=settings');
        exit();
    }

    if ($action === 'save_user') {
        $current = current_user();
        $targetId = $_POST['id'] ?? '';
        $isAdmin = $current && $current['role'] === 'admin';
        if (!$isAdmin && $current['id'] !== $targetId) {
            require_admin();
        }
        $payload = [
            'nickname' => trim($_POST['nickname'] ?? '')
        ];
        if ($isAdmin) {
            if (isset($_POST['username'])) {
                $payload['username'] = trim($_POST['username'] ?? '');
            }
            if (isset($_POST['role'])) {
                $payload['role'] = $_POST['role'] ?? 'guest';
            }
        }
        if (!empty($_POST['avatar_clear'])) {
            $payload['avatar'] = '';
        }
        $avatarUpload = handle_upload('avatar_file');
        if ($avatarUpload) {
            $payload['avatar'] = $avatarUpload;
        }
        $password = $_POST['password'] ?? '';
        if ($password) {
            $payload['password_hash'] = password_hash($password, PASSWORD_DEFAULT);
        }
        $users = update_item($users, $targetId, $payload);
        save_data('users.json', $users);
        if ($current && $current['id'] === $targetId) {
            $_SESSION['user'] = find_by_id($users, $targetId);
        }
        header('Location: ?page=users');
        exit();
    }

    if ($action === 'add_user') {
        require_admin();
        $avatarUpload = handle_upload('avatar_file');
        $users[] = [
            'id' => uniqid('u_'),
            'username' => trim($_POST['username'] ?? ''),
            'password_hash' => password_hash($_POST['password'] ?? '123456', PASSWORD_DEFAULT),
            'role' => $_POST['role'] ?? 'guest',
            'nickname' => trim($_POST['nickname'] ?? ''),
            'avatar' => $avatarUpload
        ];
        save_data('users.json', $users);
        header('Location: ?page=users');
        exit();
    }

    if ($action === 'delete_user') {
        require_admin();
        $id = $_POST['id'] ?? '';
        $users = delete_item($users, $id);
        save_data('users.json', $users);
        header('Location: ?page=users');
        exit();
    }
// --- 新增代码开始：批量下载功能 ---
    if ($action === 'download_images') {
            require_admin(); // 确保只有管理员可以使用，如果想开放给所有用户，请移除此行
            $imageIds = $_POST['image_ids'] ?? [];
            
            // 过滤出有效的图片数据
            $validImages = array_filter($images, fn($img) => in_array($img['id'], $imageIds));
    
            if (!$validImages) {
                $errors[] = '请至少选择一张图片。';
            } elseif (!class_exists('ZipArchive')) {
                $errors[] = '服务器未安装 php-zip 扩展，无法打包下载。';
            } else {
                $zip = new ZipArchive();
                // 在系统临时目录创建一个临时 ZIP 文件
                $zipName = 'gallery_' . date('Ymd_His') . '.zip';
                $tempFile = sys_get_temp_dir() . '/' . $zipName;
    
                if ($zip->open($tempFile, ZipArchive::CREATE | ZipArchive::OVERWRITE) === TRUE) {
                    foreach ($validImages as $img) {
                        // 将 URL 路径 (/uploads/xxx.jpg) 转换为本地文件系统绝对路径
                        $fileName = basename($img['path']);
                        $localPath = UPLOAD_PATH . '/' . $fileName;
                        
                        if (file_exists($localPath)) {
                            $zip->addFile($localPath, $fileName);
                        }
                    }
                    $zip->close();
    
                    // 检查文件是否生成成功并输出给浏览器
                    if (file_exists($tempFile)) {
                        // 清除之前的输出缓冲，防止 ZIP 文件损坏
                        if (ob_get_level()) ob_end_clean();
                        
                        header('Content-Description: File Transfer');
                        header('Content-Type: application/zip');
                        header('Content-Disposition: attachment; filename="' . $zipName . '"');
                        header('Expires: 0');
                        header('Cache-Control: must-revalidate');
                        header('Pragma: public');
                        header('Content-Length: ' . filesize($tempFile));
                        
                        readfile($tempFile);
                        unlink($tempFile); // 下载完成后删除临时文件
                        exit;
                    } else {
                        $errors[] = '打包失败，临时文件无法生成。';
                    }
                } else {
                    $errors[] = '无法创建 ZIP 文件。';
                }
            }
        }
        // --- 新增代码结束 ---
    
    if ($action === 'create_share') {
        require_admin();
        $imageIds = $_POST['image_ids'] ?? [];
        $ttlHours = max(1, (int)($_POST['ttl_hours'] ?? 24));
        $validIds = array_values(array_filter($imageIds, fn($id) => find_by_id($images, $id)));
        if (!$validIds) {
            $errors[] = '请选择需要分享的图片。';
        } else {
            $token = bin2hex(random_bytes(12));
            $shares[] = [
                'token' => $token,
                'image_ids' => $validIds,
                'expires_at' => time() + ($ttlHours * 3600)
            ];
            save_data('shares.json', $shares);
            header('Location: ?page=share&token=' . urlencode($token));
            exit();
        }
    }
}

if ($page === 'logout') {
    session_destroy();
    header('Location: ?page=login');
    exit();
}

$user = current_user();
$siteName = $settings['site_name'] ?? '私密画廊';
$favicon = $settings['favicon'] ?? '';

$bgImages = $settings['login_backgrounds']['images'] ?? [];
$bgMode = $settings['login_backgrounds']['mode'] ?? 'random';
$loginBg = '';
if ($bgImages) {
    if ($bgMode === 'fixed') {
        $loginBg = $bgImages[0] ?? '';
    } else {
        $loginBg = $bgImages[array_rand($bgImages)] ?? '';
    }
}

function render_header(string $title, string $siteName, string $favicon): void {
    $icon = $favicon ? '<link rel="icon" href="' . htmlspecialchars($favicon) . '">' : '';
    echo "<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">";
    echo "<title>" . htmlspecialchars($title) . "</title>" . $icon . "<link rel=\"stylesheet\" href=\"assets/styles.css\"></head><body>";
}

function render_nav(array $user, string $siteName): void {
    echo '<header class="site-header">';
    echo '<a class="brand" href="?page=gallery">' . htmlspecialchars($siteName) . '</a>';
    echo '<nav>';
    echo '<a href="?page=gallery">画廊</a>';
    echo '<a href="?page=works">作品</a>';
    echo '<a href="?page=characters">角色</a>';
    echo '<a href="?page=users">用户</a>';
    echo '</nav>';
    echo '<div class="user-chip">';
    echo '<button class="user-menu-trigger" type="button" aria-haspopup="true" aria-expanded="false">';
    if (!empty($user['avatar'])) {
        echo '<img src="' . htmlspecialchars($user['avatar']) . '" alt="avatar">';
    } else {
        echo '<span class="avatar-placeholder">' . htmlspecialchars(mb_substr($user['nickname'] ?: $user['username'], 0, 1)) . '</span>';
    }
    echo '<div><strong>' . htmlspecialchars($user['nickname'] ?: $user['username']) . '</strong></div>';
    echo '</button>';
    echo '<div class="user-menu">';
    echo '<a href="?page=users">用户设置</a>';
    if ($user['role'] === 'admin') {
        echo '<a href="?page=settings">管理员设置</a>';
    }
    echo '<a href="?page=logout" class="danger-link">退出</a>';
    echo '</div>';
    echo '</div>';
    echo '</header>';
}

function render_footer(string $copyright): void {
    echo '<footer class="site-footer">' . htmlspecialchars($copyright) . '</footer>';
    echo '<script src="assets/app.js"></script>';
    echo '</body></html>';
}

if ($page === 'login') {
    render_header('登录 · ' . $siteName, $siteName, $favicon);
    $bgStyle = $loginBg ? 'style="background-image: url(' . htmlspecialchars($loginBg) . ');"' : '';
    echo '<div class="login-page" ' . $bgStyle . '>';
    echo '<div class="login-card">';
    echo '<h1>' . htmlspecialchars($siteName) . '</h1>';
    echo '<p class="login-subtitle">私人二次元画廊 · 仅限授权用户访问</p>';
    if ($errors) {
        echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
    }
    echo '<form method="post" enctype="multipart/form-data">';
    echo '<input type="hidden" name="action" value="login">';
    echo '<label>用户名<input name="username" required></label>';
    echo '<label>密码<input name="password" type="password" required></label>';
    echo '<button type="submit">进入画廊</button>';
    echo '</form>';
    echo '<div class="login-hint">默认账号：admin / guest 密码：admin123</div>';
    echo '</div>';
    echo '</div>';
    echo '</body></html>';
    exit();
}

render_header($page . ' · ' . $siteName, $siteName, $favicon);
render_nav($user, $siteName);

echo '<main class="site-main">';

if ($page === 'gallery') {
    $preferred = $settings['gallery_preferences']['character_ids'] ?? [];
    $filtered = $images;
    if ($preferred) {
        $filtered = array_values(array_filter($images, fn($img) => in_array($img['character_id'], $preferred, true)));
    }
    if (!$filtered) {
        $filtered = $images;
    }
    shuffle($filtered);
    echo '<section class="section">';
    echo '<div class="section-header"><div><h2>今日随机画廊</h2><p>基于管理员偏好角色动态随机。</p></div></div>';
    echo '<div class="gallery-grid">';
    foreach (array_slice($filtered, 0, 12) as $img) {
        $character = find_by_id($characters, $img['character_id']);
        $work = find_by_id($works, $img['work_id']);
        echo '<a class="gallery-card gallery-link" href="?page=image&id=' . urlencode($img['id']) . '">';
        echo '<img src="' . htmlspecialchars($img['path']) . '" alt="画廊图片">';
        echo '<div class="gallery-overlay">';
        echo '<span>' . htmlspecialchars($work['name'] ?? '') . '</span>';
        echo '<span>' . htmlspecialchars($character['name'] ?? '') . '</span>';
        echo '</div>';
        echo '</a>';
    }
    echo '</div>';
    echo '</section>';
}

if ($page === 'works') {
    echo '<section class="section">';
    echo '<div class="section-header"><div><h2>作品管理</h2></div>';
    if ($user['role'] === 'admin') {
        echo '<a class="btn-primary" href="?page=manage_works">管理</a>';
    }
    echo '</div>';
    if ($errors) {
        echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
    }
    echo '<div class="work-grid">';
    foreach ($works as $work) {
        echo '<a class="work-card" href="?page=work&id=' . urlencode($work['id']) . '">';
        echo '<img src="' . htmlspecialchars($work['poster']) . '" alt="' . htmlspecialchars($work['name']) . '">';
        $aliasText = !empty($work['alias']) ? '<span class="alias">' . htmlspecialchars($work['alias']) . '</span>' : '';
        echo '<div class="work-meta"><h3>' . htmlspecialchars($work['name']) . $aliasText . '</h3><p>' . htmlspecialchars($work['description']) . '</p></div>';
        echo '</a>';
    }
    echo '</div>';
    echo '</section>';
}

if ($page === 'work') {
    $workId = $_GET['id'] ?? '';
    $work = find_by_id($works, $workId);
    if ($work) {
        echo '<section class="section">';
        echo '<div class="work-hero">';
        echo '<img src="' . htmlspecialchars($work['poster']) . '" alt="' . htmlspecialchars($work['name']) . '">';
        $aliasLine = !empty($work['alias']) ? '<span class="alias">' . htmlspecialchars($work['alias']) . '</span>' : '';
        echo '<div><h2>' . htmlspecialchars($work['name']) . $aliasLine . '</h2><p>' . htmlspecialchars($work['description']) . '</p></div>';
        echo '</div>';
        $related = array_values(array_filter($characters, fn($c) => $c['work_id'] === $workId));
        if ($errors) {
            echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
        }
        echo '<div class="section-header"><h3>角色列表</h3><p>进入角色管理或浏览图片。</p></div>';
        echo '<div class="character-grid">';
        foreach ($related as $character) {
            echo '<a class="character-card" href="?page=character&id=' . urlencode($character['id']) . '">';
            echo '<img src="' . htmlspecialchars($character['avatar']) . '" alt="' . htmlspecialchars($character['name']) . '">';
            echo '<div>' . htmlspecialchars($character['name']) . '</div>';
            echo '</a>';
        }
        echo '</div>';
        echo '</section>';
    }
}

if ($page === 'character') {
    $characterId = $_GET['id'] ?? '';
    $character = find_by_id($characters, $characterId);
    if ($character) {
        $work = find_by_id($works, $character['work_id']);
        echo '<section class="section">';
        echo '<div class="character-hero">';
        echo '<img src="' . htmlspecialchars($character['avatar']) . '" alt="' . htmlspecialchars($character['name']) . '">';
        echo '<div><h2>' . htmlspecialchars($character['name']) . '</h2><p>' . htmlspecialchars($work['name'] ?? '') . '</p></div>';
        echo '</div>';
        $related = array_values(array_filter($images, fn($img) => $img['character_id'] === $characterId));
        if ($errors) {
            echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
        }
        echo '<div class="section-header"><h3>角色图片</h3><p>支持拖拽上传或选择文件。</p></div>';
        echo '<div class="gallery-grid">';
        foreach ($related as $img) {
            echo '<a class="gallery-card gallery-link" href="?page=image&id=' . urlencode($img['id']) . '">';
            echo '<img src="' . htmlspecialchars($img['path']) . '" alt="角色图片">';
            echo '<div class="gallery-overlay">';
            echo '<span>' . htmlspecialchars($work['name'] ?? '') . '</span>';
            echo '<span>' . htmlspecialchars($character['name'] ?? '') . '</span>';
            echo '</div>';
            echo '</a>';
        }
        echo '</div>';
        if ($user['role'] === 'admin') {
            echo '<div class="admin-panel">';
            echo '<h3>新增图片</h3>';
            echo '<form method="post" enctype="multipart/form-data" class="dropzone">';
            echo '<input type="hidden" name="action" value="add_image">';
            echo '<input type="hidden" name="character_id" value="' . htmlspecialchars($characterId) . '">';
            echo '<input type="hidden" name="work_id" value="' . htmlspecialchars($character['work_id']) . '">';
            echo '<div class="form-grid">';
            echo '<label>选择图片<input type="file" name="image_files[]" accept="image/*" multiple required></label>';
            echo '</div>';
            echo '<p class="hint">将图片拖拽到此区域即可批量上传。</p>';
            echo '<button type="submit">保存图片</button>';
            echo '</form>';
            echo '</div>';
        }
        echo '</section>';
    }
}

if ($page === 'characters') {
    echo '<section class="section">';
    echo '<div class="section-header"><div><h2>角色画廊</h2></div>';
    if ($user['role'] === 'admin') {
        echo '<a class="btn-primary" href="?page=manage_characters">管理</a>';
    }
    echo '</div>';
    echo '<div class="character-grid">';
    foreach ($characters as $character) {
        $work = find_by_id($works, $character['work_id']);
        echo '<a class="character-card" href="?page=character&id=' . urlencode($character['id']) . '">';
        echo '<img src="' . htmlspecialchars($character['avatar']) . '" alt="' . htmlspecialchars($character['name']) . '">';
        echo '<div>' . htmlspecialchars($character['name']) . '</div>';
        if (!empty($work['name'])) {
            echo '<div class="muted">' . htmlspecialchars($work['name']) . '</div>';
        }
        echo '</a>';
    }
    echo '</div>';
    echo '</section>';
}

if ($page === 'manage_works') {
    require_admin();
    echo '<section class="section">';
    echo '<div class="section-header"><h2>作品管理中心</h2><p>新增与维护作品。</p></div>';
    if ($errors) {
        echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
    }
    echo '<div class="admin-split">';
    echo '<div class="admin-panel">';
    echo '<h3>新增作品</h3>';
    echo '<form method="post" enctype="multipart/form-data">';
    echo '<input type="hidden" name="action" value="add_work">';
    echo '<div class="form-grid">';
    echo '<label>名称<input name="name" required></label>';
    echo '<label>海报上传<input type="file" name="poster" accept="image/*" required></label>';
    echo '<label>别名<input name="alias"></label>';
    echo '<label class="span">简介<textarea name="description"></textarea></label>';
    echo '</div>';
    echo '<button type="submit">保存作品</button>';
    echo '</form>';
    echo '</div>';
    echo '<div class="admin-panel">';
    echo '<h3>现有作品</h3>';
    foreach ($works as $work) {
        echo '<form method="post" class="inline-form" enctype="multipart/form-data">';
        echo '<input type="hidden" name="action" value="update_work">';
        echo '<input type="hidden" name="id" value="' . htmlspecialchars($work['id']) . '">';
        echo '<input name="name" value="' . htmlspecialchars($work['name']) . '">';
        echo '<input type="file" name="poster" accept="image/*">';
        echo '<input name="alias" value="' . htmlspecialchars($work['alias'] ?? '') . '">';
        echo '<input name="description" value="' . htmlspecialchars($work['description']) . '">';
        echo '<button type="submit">更新</button>';
        echo '</form>';
        echo '<form method="post" class="inline-form">';
        echo '<input type="hidden" name="action" value="delete_work">';
        echo '<input type="hidden" name="id" value="' . htmlspecialchars($work['id']) . '">';
        echo '<button type="submit" class="danger">删除</button>';
        echo '</form>';
    }
    echo '</div>';
    echo '</div>';
    echo '</section>';
}

if ($page === 'manage_characters') {
    require_admin();
    echo '<section class="section">';
    echo '<div class="section-header"><h2>角色管理中心</h2><p>新增与维护角色。</p></div>';
    if ($errors) {
        echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
    }
    echo '<div class="admin-split">';
    echo '<div class="admin-panel">';
    echo '<h3>新增角色</h3>';
    echo '<form method="post" enctype="multipart/form-data">';
    echo '<input type="hidden" name="action" value="add_character">';
    echo '<div class="form-grid">';
    echo '<label>所属作品<select name="work_id" required>';
    foreach ($works as $work) {
        echo '<option value="' . htmlspecialchars($work['id']) . '">' . htmlspecialchars($work['name']) . '</option>';
    }
    echo '</select></label>';
    echo '<label>名称<input name="name" required></label>';
    echo '<label>头像上传<input type="file" name="avatar" accept="image/*" required></label>';
    echo '</div>';
    echo '<button type="submit">保存角色</button>';
    echo '</form>';
    echo '</div>';
    echo '<div class="admin-panel">';
    echo '<h3>现有角色</h3>';
    foreach ($characters as $character) {
        echo '<form method="post" class="inline-form" enctype="multipart/form-data">';
        echo '<input type="hidden" name="action" value="update_character">';
        echo '<input type="hidden" name="id" value="' . htmlspecialchars($character['id']) . '">';
        echo '<input type="hidden" name="work_id" value="' . htmlspecialchars($character['work_id']) . '">';
        echo '<input name="name" value="' . htmlspecialchars($character['name']) . '">';
        echo '<input type="file" name="avatar" accept="image/*">';
        echo '<button type="submit">更新</button>';
        echo '</form>';
        echo '<form method="post" class="inline-form">';
        echo '<input type="hidden" name="action" value="delete_character">';
        echo '<input type="hidden" name="id" value="' . htmlspecialchars($character['id']) . '">';
        echo '<input type="hidden" name="work_id" value="' . htmlspecialchars($character['work_id']) . '">';
        echo '<button type="submit" class="danger">删除</button>';
        echo '</form>';
    }
    echo '</div>';
    echo '</div>';
    echo '</section>';
}

if ($page === 'manage_images') {
    require_admin();
    echo '<section class="section">';
    echo '<div class="section-header"><h2>图片管理中心</h2><p>新增与维护图片。</p></div>';
    if ($errors) {
        echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
    }
    echo '<div class="admin-split">';
    echo '<div class="admin-panel">';
    echo '<h3>新增图片</h3>';
    echo '<form method="post" enctype="multipart/form-data" class="dropzone">';
    echo '<input type="hidden" name="action" value="add_image">';
    echo '<div class="form-grid">';
    echo '<label>所属角色<select name="character_id" required>';
    foreach ($characters as $character) {
        $work = find_by_id($works, $character['work_id']);
        $label = ($work['name'] ?? '') . ' · ' . ($character['name'] ?? '');
        echo '<option value="' . htmlspecialchars($character['id']) . '">' . htmlspecialchars($label) . '</option>';
    }
    echo '</select></label>';
    echo '<label>选择图片<input type="file" name="image_files[]" accept="image/*" multiple required></label>';
    echo '</div>';
    echo '<p class="hint">将图片拖拽到此区域即可批量上传。</p>';
    echo '<button type="submit">保存图片</button>';
    echo '</form>';
    echo '</div>';
    echo '<div class="admin-panel">';
    echo '<h3>现有图片</h3>';
    echo '<form method="post" class="share-panel">';
    echo '<input type="hidden" name="action" value="create_share">';
    echo '<div class="share-toolbar">';
    echo '<label>有效时间<select name="ttl_hours">';
    echo '<option value="1">1小时</option>';
    echo '<option value="6">6小时</option>';
    echo '<option value="24" selected>24小时</option>';
    echo '<option value="168">7天</option>';
    echo '</select></label>';
    echo '<button type="submit" class="btn-primary">生成分享链接</button>';
    echo '</div>';
    echo '<div class="gallery-grid selectable-grid">';
    foreach ($images as $img) {
        $work = find_by_id($works, $img['work_id']);
        $character = find_by_id($characters, $img['character_id']);
        echo '<label class="gallery-card gallery-select">';
        echo '<input type="checkbox" name="image_ids[]" value="' . htmlspecialchars($img['id']) . '">';
        echo '<img src="' . htmlspecialchars($img['path']) . '" alt="图片">';
        echo '<div class="gallery-overlay">';
        echo '<span>' . htmlspecialchars($work['name'] ?? '') . '</span>';
        echo '<span>' . htmlspecialchars($character['name'] ?? '') . '</span>';
        echo '</div>';
        echo '</label>';
    }
    echo '</div>';
    echo '</form>';
    echo '</div>';
    echo '</div>';
    echo '</section>';
}

if ($page === 'image') {
    $imageId = $_GET['id'] ?? '';
    $image = find_by_id($images, $imageId);
    if ($image) {
        $work = find_by_id($works, $image['work_id']);
        $character = find_by_id($characters, $image['character_id']);
        echo '<section class="section image-view">';
        echo '<div class="section-header"><h2>原图预览</h2><p>' . htmlspecialchars($work['name'] ?? '') . ' · ' . htmlspecialchars($character['name'] ?? '') . '</p></div>';
        echo '<div class="image-viewer">';
        echo '<img src="' . htmlspecialchars($image['path']) . '" alt="原图">';
        echo '</div>';
        if ($user['role'] === 'admin') {
            if ($errors) {
                echo '<div class="alert">' . htmlspecialchars($errors[0]) . '</div>';
            }
            echo '<div class="admin-panel">';
            echo '<h3>替换图片</h3>';
            echo '<form method="post" enctype="multipart/form-data">';
            echo '<input type="hidden" name="action" value="update_image">';
            echo '<input type="hidden" name="id" value="' . htmlspecialchars($imageId) . '">';
            echo '<input type="hidden" name="character_id" value="' . htmlspecialchars($image['character_id']) . '">';
            echo '<div class="form-grid">';
            echo '<label>上传新图片<input type="file" name="image_file" accept="image/*" required></label>';
            echo '</div>';
            echo '<button type="submit">保存替换</button>';
            echo '</form>';
            echo '<h3>删除图片</h3>';
            echo '<form method="post">';
            echo '<input type="hidden" name="action" value="delete_image">';
            echo '<input type="hidden" name="id" value="' . htmlspecialchars($imageId) . '">';
            echo '<input type="hidden" name="character_id" value="' . htmlspecialchars($image['character_id']) . '">';
            echo '<input type="hidden" name="redirect" value="?page=gallery">';
            echo '<button type="submit" class="danger">删除</button>';
            echo '</form>';
            echo '</div>';
        }
        echo '</section>';
    }
}

if ($page === 'share') {
    $token = $_GET['token'] ?? '';
    $share = null;
    foreach ($shares as $entry) {
        if ($entry['token'] === $token) {
            $share = $entry;
            break;
        }
    }
    if ($share && ($share['expires_at'] ?? 0) > time()) {
        $shareImages = array_values(array_filter($images, fn($img) => in_array($img['id'], $share['image_ids'] ?? [], true)));
        render_header('分享画廊', $siteName, $favicon);
        echo '<main class="site-main">';
        echo '<section class="section">';
        echo '<div class="section-header"><div><h2>分享画廊</h2></div></div>';
        echo '<div class="gallery-grid">';
        foreach ($shareImages as $img) {
            echo '<div class="gallery-card gallery-share">';
            echo '<img src="' . htmlspecialchars($img['path']) . '" alt="分享图片">';
            echo '<div class="gallery-actions">';
            echo '<a class="btn-primary" href="' . htmlspecialchars($img['path']) . '" download>下载</a>';
            echo '</div>';
            echo '</div>';
        }
        echo '</div>';
        echo '</section>';
        echo '</main>';
        render_footer($settings['copyright'] ?? '');
        exit();
    }
    render_header('分享已失效', $siteName, $favicon);
    echo '<main class="site-main"><section class="section"><h2>分享链接已失效或不存在。</h2></section></main>';
    render_footer($settings['copyright'] ?? '');
    exit();
}

if ($page === 'users') {
    echo '<section class="section">';
    echo '<div class="section-header"><h2>用户中心</h2><p>管理员可维护账号与权限。</p></div>';
    echo '<div class="user-grid">';
    foreach ($users as $u) {
        echo '<a class="user-card" href="?page=user&id=' . urlencode($u['id']) . '">';
        echo '<div class="user-avatar">';
        if (!empty($u['avatar'])) {
            echo '<img src="' . htmlspecialchars($u['avatar']) . '" alt="avatar">';
        } else {
            echo '<span>' . htmlspecialchars(mb_substr($u['nickname'] ?: $u['username'], 0, 1)) . '</span>';
        }
        echo '</div>';
        echo '<div><strong>' . htmlspecialchars($u['nickname'] ?: $u['username']) . '</strong><p>' . htmlspecialchars($u['role']) . '</p></div>';
        echo '</a>';
    }
    echo '</div>';
    echo '<div class="admin-panel">';
    echo '<h3>编辑我的资料</h3>';
    echo '<form method="post" enctype="multipart/form-data">';
    echo '<input type="hidden" name="action" value="save_user">';
    echo '<input type="hidden" name="id" value="' . htmlspecialchars($user['id']) . '">';
    echo '<div class="form-grid">';
    echo '<label>昵称<input name="nickname" value="' . htmlspecialchars($user['nickname']) . '"></label>';
    echo '<label>头像上传<input type="file" name="avatar_file" accept="image/*"></label>';
    echo '<label>新密码<input name="password" type="password"></label>';
    echo '<label><input type="checkbox" name="avatar_clear" value="1"> 清除头像</label>';
    echo '</div>';
    echo '<button type="submit">保存</button>';
    echo '</form>';
    if ($user['role'] === 'admin') {
        echo '<h3>管理员用户管理</h3>';
        foreach ($users as $u) {
            echo '<form method="post" class="inline-form" enctype="multipart/form-data">';
            echo '<input type="hidden" name="action" value="save_user">';
            echo '<input type="hidden" name="id" value="' . htmlspecialchars($u['id']) . '">';
            echo '<input name="username" value="' . htmlspecialchars($u['username']) . '">';
            echo '<input name="nickname" value="' . htmlspecialchars($u['nickname']) . '">';
            echo '<input type="file" name="avatar_file" accept="image/*">';
            echo '<select name="role">';
            echo '<option value="admin"' . ($u['role'] === 'admin' ? ' selected' : '') . '>admin</option>';
            echo '<option value="guest"' . ($u['role'] === 'guest' ? ' selected' : '') . '>guest</option>';
            echo '</select>';
            echo '<input name="password" type="password" placeholder="重置密码">';
            echo '<label class="checkbox-inline"><input type="checkbox" name="avatar_clear" value="1">清除头像</label>';
            echo '<button type="submit">更新</button>';
            echo '</form>';
            echo '<form method="post" class="inline-form">';
            echo '<input type="hidden" name="action" value="delete_user">';
            echo '<input type="hidden" name="id" value="' . htmlspecialchars($u['id']) . '">';
            echo '<button type="submit" class="danger">删除</button>';
            echo '</form>';
        }
        echo '<h3>新增用户</h3>';
        echo '<form method="post" class="inline-form" enctype="multipart/form-data">';
        echo '<input type="hidden" name="action" value="add_user">';
        echo '<input name="username" placeholder="用户名" required>'; 
        echo '<input name="nickname" placeholder="昵称">';
        echo '<input type="file" name="avatar_file" accept="image/*">';
        echo '<select name="role"><option value="guest">guest</option><option value="admin">admin</option></select>';
        echo '<input name="password" type="password" placeholder="初始密码">';
        echo '<button type="submit">创建</button>';
        echo '</form>';
    }
    echo '</div>';
    echo '</section>';
}

if ($page === 'user') {
    $targetId = $_GET['id'] ?? '';
    $target = find_by_id($users, $targetId);
    if ($target) {
        $isAdmin = $user['role'] === 'admin';
        if (!$isAdmin && $user['id'] !== $targetId) {
            require_admin();
        }
        echo '<section class="section">';
        echo '<div class="section-header"><h2>账号详情</h2><p>编辑账号资料与权限。</p></div>';
        echo '<div class="admin-panel">';
        echo '<form method="post" enctype="multipart/form-data">';
        echo '<input type="hidden" name="action" value="save_user">';
        echo '<input type="hidden" name="id" value="' . htmlspecialchars($target['id']) . '">';
        echo '<div class="form-grid">';
        if ($isAdmin) {
            echo '<label>用户名<input name="username" value="' . htmlspecialchars($target['username']) . '"></label>';
            echo '<label>权限<select name="role">';
            echo '<option value="admin"' . ($target['role'] === 'admin' ? ' selected' : '') . '>admin</option>';
            echo '<option value="guest"' . ($target['role'] === 'guest' ? ' selected' : '') . '>guest</option>';
            echo '</select></label>';
        }
        echo '<label>昵称<input name="nickname" value="' . htmlspecialchars($target['nickname']) . '"></label>';
        echo '<label>头像上传<input type="file" name="avatar_file" accept="image/*"></label>';
        echo '<label>新密码<input name="password" type="password"></label>';
        echo '<label><input type="checkbox" name="avatar_clear" value="1"> 清除头像</label>';
        echo '</div>';
        echo '<button type="submit">保存</button>';
        echo '</form>';
        if ($isAdmin) {
            echo '<form method="post" class="inline-form">';
            echo '<input type="hidden" name="action" value="delete_user">';
            echo '<input type="hidden" name="id" value="' . htmlspecialchars($target['id']) . '">';
            echo '<button type="submit" class="danger">删除账号</button>';
            echo '</form>';
        }
        echo '</div>';
        echo '</section>';
    }
}

if ($page === 'settings') {
    require_admin();
    echo '<section class="section">';
    echo '<div class="section-header"><h2>系统设置</h2><p>配置站点外观与登录背景。</p></div>';
    echo '<form method="post" class="admin-panel" enctype="multipart/form-data">';
    echo '<input type="hidden" name="action" value="update_settings">';
    echo '<div class="form-grid">';
    echo '<label>站点名称<input name="site_name" value="' . htmlspecialchars($settings['site_name'] ?? '') . '"></label>';
    echo '<label>站点图标上传<input type="file" name="favicon_file" accept="image/*,.ico"></label>';
    echo '<label>版权信息<input name="copyright" value="' . htmlspecialchars($settings['copyright'] ?? '') . '"></label>';
    echo '<label>登录背景模式<select name="bg_mode">';
    echo '<option value="random"' . (($settings['login_backgrounds']['mode'] ?? '') === 'random' ? ' selected' : '') . '>随机轮播</option>';
    echo '<option value="fixed"' . (($settings['login_backgrounds']['mode'] ?? '') === 'fixed' ? ' selected' : '') . '>固定第一张</option>';
    echo '</select></label>';
    echo '<label class="span">上传登录背景<input type="file" name="bg_images[]" accept="image/*" multiple></label>';
    echo '<label><input type="checkbox" name="reset_bg" value="1"> 清空背景列表</label>';
    echo '<label><input type="checkbox" name="favicon_clear" value="1"> 清空站点图标</label>';
    echo '<label class="span">画廊偏好角色 (按住Ctrl多选)<select name="preference_ids[]" multiple size="5">';
    foreach ($characters as $c) {
        $selected = in_array($c['id'], $settings['gallery_preferences']['character_ids'] ?? [], true) ? ' selected' : '';
        echo '<option value="' . htmlspecialchars($c['id']) . '"' . $selected . '>' . htmlspecialchars($c['name']) . '</option>';
    }
    echo '</select></label>';
    echo '</div>';
    $bgList = $settings['login_backgrounds']['images'] ?? [];
    if ($bgList) {
        echo '<div class="image-list"><h4>当前登录背景</h4><div class="image-list-grid">';
        foreach ($bgList as $bg) {
            echo '<div class="image-list-item"><img src="' . htmlspecialchars($bg) . '" alt="背景"></div>';
        }
        echo '</div></div>';
    }
    if (!empty($settings['favicon'])) {
        echo '<div class="image-list"><h4>当前站点图标</h4><div class="image-list-grid">';
        echo '<div class="image-list-item"><img src="' . htmlspecialchars($settings['favicon']) . '" alt="图标"></div>';
        echo '</div></div>';
    }
    echo '<button type="submit">保存设置</button>';
    echo '</form>';
    echo '</section>';
}

echo '</main>';

render_footer($settings['copyright'] ?? '');
