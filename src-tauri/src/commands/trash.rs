use crate::error::AppError;
use serde::Serialize;
use std::collections::HashSet;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TrashItemError {
    code: &'static str,
    message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TrashBatchResult {
    succeeded: usize,
    failed: usize,
    errors: Vec<TrashItemError>,
}

fn dangerous_system_prefixes() -> Vec<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        ["WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"]
            .into_iter()
            .filter_map(std::env::var_os)
            .map(PathBuf::from)
            .collect()
    }
    #[cfg(target_os = "macos")]
    {
        vec![
            PathBuf::from("/System"),
            PathBuf::from("/Library"),
            PathBuf::from("/Applications"),
        ]
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        vec![
            PathBuf::from("/bin"),
            PathBuf::from("/etc"),
            PathBuf::from("/usr"),
        ]
    }
}

fn validate_path(path: &Path) -> Result<PathBuf, AppError> {
    if path.as_os_str().is_empty() || !path.is_absolute() {
        return Err(AppError::new("invalid_path", "只接受非空的绝对路径"));
    }
    let link_metadata = std::fs::symlink_metadata(path)
        .map_err(|_| AppError::new("not_found", "文件不存在或不可访问"))?;
    if link_metadata.file_type().is_symlink() {
        return Err(AppError::new("symlink_rejected", "MVP 不支持符号链接"));
    }
    if !link_metadata.is_file() {
        return Err(AppError::new(
            "not_a_file",
            "MVP 只支持普通文件，不支持文件夹",
        ));
    }
    let canonical = path
        .canonicalize()
        .map_err(|_| AppError::new("invalid_path", "无法规范化文件路径"))?;
    if canonical.parent().is_none() {
        return Err(AppError::new("dangerous_path", "拒绝磁盘根路径"));
    }
    if dirs::home_dir().is_some_and(|home| canonical == home) {
        return Err(AppError::new("dangerous_path", "拒绝用户主目录"));
    }
    if dangerous_system_prefixes()
        .iter()
        .any(|prefix| canonical.starts_with(prefix))
    {
        return Err(AppError::new("protected_path", "拒绝系统保护目录中的文件"));
    }
    if let Ok(executable) = std::env::current_exe() {
        if executable
            .parent()
            .is_some_and(|app_dir| canonical.starts_with(app_dir))
        {
            return Err(AppError::new(
                "application_path",
                "拒绝移动应用自身目录中的文件",
            ));
        }
    }
    Ok(canonical)
}

#[tauri::command]
pub async fn move_paths_to_trash(paths: Vec<String>) -> TrashBatchResult {
    let mut seen = HashSet::new();
    let mut result = TrashBatchResult {
        succeeded: 0,
        failed: 0,
        errors: Vec::new(),
    };
    for raw in paths {
        if !seen.insert(raw.clone()) {
            continue;
        }
        match validate_path(Path::new(&raw)) {
            Ok(path) => match trash::delete(path) {
                Ok(()) => result.succeeded += 1,
                Err(_) => {
                    result.failed += 1;
                    result.errors.push(TrashItemError {
                        code: "trash_failed",
                        message: "系统回收站拒绝了该文件".into(),
                    });
                }
            },
            Err(error) => {
                result.failed += 1;
                result.errors.push(TrashItemError {
                    code: error.code,
                    message: error.message,
                });
            }
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn rejects_empty_and_relative_paths() {
        assert_eq!(
            validate_path(Path::new("")).unwrap_err().code,
            "invalid_path"
        );
        assert_eq!(
            validate_path(Path::new("relative.txt")).unwrap_err().code,
            "invalid_path"
        );
    }

    #[test]
    fn accepts_regular_temp_file_without_trashing_it() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("安全 文件.txt");
        std::fs::File::create(&path)
            .unwrap()
            .write_all(b"test")
            .unwrap();
        assert_eq!(validate_path(&path).unwrap(), path.canonicalize().unwrap());
        assert!(path.exists());
    }

    #[test]
    fn rejects_directories_and_symlinks() {
        let directory = tempfile::tempdir().unwrap();
        assert_eq!(
            validate_path(directory.path()).unwrap_err().code,
            "not_a_file"
        );
        #[cfg(unix)]
        {
            let target = directory.path().join("target");
            std::fs::write(&target, b"x").unwrap();
            let link = directory.path().join("link");
            std::os::unix::fs::symlink(&target, &link).unwrap();
            assert_eq!(validate_path(&link).unwrap_err().code, "symlink_rejected");
        }
    }
}
