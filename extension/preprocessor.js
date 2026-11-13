/**
 * 세부능력및특기사항 Excel 파일 전처리 모듈
 * - Type1: 과목별 파일 (컬럼: 과목, 학년, 학기, 번호, 성명, 내용)
 * - Type2: 통합 파일 (컬럼: 번호, 성명, 학년, 세부능력및특기사항)
 * - 반복되는 헤더 제거
 * - 페이지 마커 행 제거
 * - 빈 셀 위에서 채우기 (forward fill)
 * - 같은 과목/학기/학생의 내용 합치기
 */

const Preprocessor = {
    /**
     * 파일명에서 학년/반 정보 추출
     */
    extractClassInfo(filename) {
        const match = filename.match(/Grade(\d+)_Class(\d+)/i);
        if (match) {
            return { grade: parseInt(match[1]), class: parseInt(match[2]) };
        }
        // 한글 패턴도 시도
        const korMatch = filename.match(/(\d)학년\s*(\d+)반/);
        if (korMatch) {
            return { grade: parseInt(korMatch[1]), class: parseInt(korMatch[2]) };
        }
        return { grade: null, class: null };
    },

    /**
     * 행이 헤더 행인지 확인 (Type1: 과목별, Type2: 통합)
     */
    isHeaderRow(row) {
        if (!row || row.length === 0) return false;
        const col0 = String(row[0] || '').trim();
        const col1 = String(row[1] || '').trim();
        // Type1 (과목별)
        if (col0 === '과 목' || col0 === '과목') return true;
        if (col1 === '학 년') return true;
        // Type2 (통합)
        if (col0 === '번 호' || col0 === '번호') {
            if (col1 === '성  명' || col1 === '성명' || col1.includes('성')) return true;
        }
        return false;
    },

    /**
     * 행이 반/학년 표시 행인지 확인
     */
    isClassInfoRow(row) {
        if (!row || row.length === 0) return false;
        const col0 = String(row[0] || '').trim();
        return /^\d학년\s*\d+반$/.test(col0);
    },

    /**
     * 행이 페이지 마커 행인지 확인 (예: "1 / 134 샘플고등학교")
     * 연속된 [숫자, "/", 숫자] 패턴을 검색
     */
    isPageMarkerRow(row) {
        if (!row || row.length < 3) return false;
        for (let i = 0; i < row.length - 2; i++) {
            if (typeof row[i] === 'number' &&
                String(row[i + 1] || '').trim() === '/' &&
                typeof row[i + 2] === 'number') {
                return true;
            }
        }
        return false;
    },

    /**
     * 행이 제목 행인지 확인
     */
    isTitleRow(row) {
        if (!row || row.length === 0) return false;
        for (let i = 0; i < row.length; i++) {
            if (String(row[i] || '').includes('학교생활기록부')) return true;
        }
        return false;
    },

    /**
     * 행이 날짜만 있는 메타데이터 행인지 확인
     */
    isDateMetadataRow(row) {
        if (!row || row.length === 0) return false;
        let hasDate = false;
        let nonEmptyCount = 0;
        for (let i = 0; i < row.length; i++) {
            const val = String(row[i] || '').trim();
            if (val !== '') nonEmptyCount++;
            if (/^\d{4}\.\d{2}\.\d{2}/.test(val)) hasDate = true;
        }
        return hasDate && nonEmptyCount <= 2;
    },

    /**
     * 행이 완전히 빈 행인지 확인 (데이터 컬럼 기준)
     */
    isEmptyDataRow(row, maxCol) {
        if (!row || row.length === 0) return true;
        const limit = maxCol !== undefined ? maxCol : 5;
        for (let i = 0; i <= limit && i < row.length; i++) {
            if (row[i] !== null && row[i] !== undefined && String(row[i]).trim() !== '') {
                return false;
            }
        }
        return true;
    },

    /**
     * 행이 사용자 정보 행인지 확인 (예: "2학년 1반" ... "사용자명 : 권민결")
     * isClassInfoRow에서 이미 처리되지만, 단독 사용자 정보 행도 처리
     */
    isUserInfoRow(row) {
        if (!row || row.length === 0) return false;
        for (let i = 0; i < row.length; i++) {
            if (String(row[i] || '').includes('사용자명')) return true;
        }
        return false;
    },

    /**
     * 제거해야 할 행인지 확인
     */
    shouldRemoveRow(row) {
        return this.isHeaderRow(row) ||
               this.isClassInfoRow(row) ||
               this.isPageMarkerRow(row) ||
               this.isTitleRow(row) ||
               this.isDateMetadataRow(row) ||
               this.isUserInfoRow(row) ||
               this.isEmptyDataRow(row);
    },

    /**
     * 파일 유형 감지
     * @param {Array} rawData - 2D 배열
     * @returns {string} - 'type1' (과목별) 또는 'type2' (통합)
     */
    detectFileType(rawData) {
        for (let i = 0; i < Math.min(10, rawData.length); i++) {
            const row = rawData[i];
            if (!row) continue;
            const col0 = String(row[0] || '').trim();
            const col1 = String(row[1] || '').trim();
            // Type2: "번 호", "성  명" 헤더
            if ((col0 === '번 호' || col0 === '번호') &&
                (col1.includes('성') || col1 === '성  명' || col1 === '성명')) {
                // Type2의 col2는 "학 년", col3은 "세부능력 및 특기사항"
                const col3 = String(row[3] || '').trim();
                if (col3.includes('세부능력') || col3.includes('특기사항')) {
                    return 'type2';
                }
            }
            // Type1: "과 목" 헤더
            if (col0 === '과 목' || col0 === '과목') {
                return 'type1';
            }
        }
        return 'type1'; // 기본값
    },

    /**
     * 텍스트에서 과목별로 분리
     * "국어: [내용]수학: [내용](1학기)통합사회: [내용]" → [{subject, semester, content}, ...]
     */
    splitBySubject(text) {
        // 1단계: 모든 "과목명: " 패턴 후보 찾기
        const regex = /((?:\(\d학기\))?[가-힣]{2,}(?:\s[가-힣]+)*(?:\s*[ⅠⅡⅢ])?):\s/g;
        const candidates = [];
        let match;
        while ((match = regex.exec(text)) !== null) {
            candidates.push({
                index: match.index,
                endIndex: match.index + match[0].length,
                name: match[1]
            });
        }

        // 2단계: 유효한 과목 위치만 필터링
        // 텍스트 시작, 마침표 뒤, 또는 한국어 문장 종결 어미 뒤에 오는 것만 인정
        const validPositions = candidates.filter(c => {
            if (c.index === 0) return true;
            // 과목명이 너무 길면 오탐으로 간주 (15자 초과)
            if (c.name.replace(/^\(\d학기\)/, '').trim().length > 15) return false;
            const before = text.substring(Math.max(0, c.index - 5), c.index);
            // 마침표 뒤
            if (/[.。]\s*$/.test(before)) return true;
            // 한국어 문장 종결 어미 뒤 (함, 임, 됨, 음, 봄, 냄, 줌)
            if (/[함임됨음봄냄줌]\s*$/.test(before)) return true;
            return false;
        });

        // 3단계: 유효 위치로 텍스트 분할
        if (validPositions.length === 0) {
            return text.trim() ? [{ subject: '기타', semester: null, content: text.trim() }] : [];
        }

        const subjects = [];
        for (let i = 0; i < validPositions.length; i++) {
            const pos = validPositions[i];
            const contentEnd = (i < validPositions.length - 1)
                ? validPositions[i + 1].index
                : text.length;
            const content = text.substring(pos.endIndex, contentEnd).trim();

            if (!content) continue;

            let subjectName = pos.name.trim();
            let semester = null;

            const semMatch = subjectName.match(/^\((\d)학기\)/);
            if (semMatch) {
                semester = parseInt(semMatch[1]);
                subjectName = subjectName.replace(/^\(\d학기\)/, '').trim();
            }

            subjects.push({ subject: subjectName, semester, content });
        }

        if (subjects.length === 0 && text.trim()) {
            subjects.push({ subject: '기타', semester: null, content: text.trim() });
        }

        return subjects;
    },

    /**
     * Type2 통합 파일 전처리 (번호, 성명, 학년, 세부능력및특기사항)
     */
    preprocessType2(rawData, filename) {
        const stats = {
            originalRows: rawData.length,
            removedRows: 0,
            finalRows: 0,
            subjects: new Set(),
            students: new Set()
        };

        const classInfo = this.extractClassInfo(filename);

        // 1. 불필요한 행 제거
        const filteredData = [];
        for (const row of rawData) {
            if (this.shouldRemoveRow(row)) {
                stats.removedRows++;
            } else {
                filteredData.push(row);
            }
        }

        // 2. Forward Fill - 번호(0), 성명(1), 학년(2)
        for (let i = 1; i < filteredData.length; i++) {
            for (const colIdx of [0, 1, 2]) {
                if (filteredData[i][colIdx] === null ||
                    filteredData[i][colIdx] === undefined ||
                    String(filteredData[i][colIdx]).trim() === '') {
                    filteredData[i][colIdx] = filteredData[i - 1][colIdx];
                }
            }
        }

        // 3. 같은 학생+학년의 내용 합치기
        const studentMap = new Map();
        for (const row of filteredData) {
            const number = row[0];
            const name = String(row[1] || '').trim();
            const grade = row[2];
            const content = String(row[3] || '').trim();

            if (!content || !name) continue;

            const key = `${number}|${name}|${grade}`;
            if (studentMap.has(key)) {
                studentMap.get(key).content += content;
            } else {
                studentMap.set(key, { number, name, grade, content });
                stats.students.add(name);
            }
        }

        // 4. 과목별 분리 및 결과 생성
        const result = [];
        for (const [key, value] of studentMap) {
            const subjects = this.splitBySubject(value.content);

            for (const { subject, semester, content } of subjects) {
                stats.subjects.add(subject);
                result.push({
                    반: classInfo.class,
                    학년: value.grade,
                    학기: semester,
                    번호: value.number,
                    성명: value.name,
                    과목: subject,
                    내용: content
                });
            }
        }

        // 5. 정렬: 번호 → 학년 → 과목 → 학기
        result.sort((a, b) => {
            if (a.번호 !== b.번호) return (a.번호 || 0) - (b.번호 || 0);
            if (a.학년 !== b.학년) return (a.학년 || 0) - (b.학년 || 0);
            if (a.과목 !== b.과목) return (a.과목 || '').localeCompare(b.과목 || '');
            return (a.학기 || 0) - (b.학기 || 0);
        });

        stats.finalRows = result.length;
        stats.subjects = Array.from(stats.subjects);
        stats.students = Array.from(stats.students);

        return { data: result, stats };
    },

    /**
     * Excel 파일 전처리 (자동 유형 감지)
     * @param {ArrayBuffer} fileBuffer - 파일 데이터
     * @param {string} filename - 파일명
     * @returns {Object} - { data: 전처리된 데이터 배열, stats: 통계 }
     */
    /**
     * 전처리 단계 정의
     */
    getStepDefinitions() {
        return [
            { id: 'parse', label: 'Excel 파일 파싱', desc: '파일을 읽어 2D 배열로 변환' },
            { id: 'extract', label: '학년/반 정보 추출', desc: '파일명에서 메타데이터 추출' },
            { id: 'filter', label: '불필요한 행 제거', desc: '헤더, 페이지 마커, 빈 행 등 제거' },
            { id: 'fixsubject', label: '잘린 과목명 병합', desc: '줄 넘김으로 분리된 과목명을 윗 행에 합침' },
            { id: 'fill', label: '빈 셀 채우기 (Forward Fill)', desc: '병합 셀로 인한 빈 칸을 위의 값으로 채움' },
            { id: 'validate', label: '내용 없는 행 제거', desc: '실질적 데이터가 없는 행 제거' },
            { id: 'merge', label: '중복 항목 병합', desc: '같은 과목/학기/학생의 내용을 하나로 합침' },
            { id: 'sort', label: '정렬 및 출력 생성', desc: '번호 → 과목 → 학기 순으로 정렬' }
        ];
    },

    preprocess(fileBuffer, filename, onStep) {
        const steps = [];
        const snapshots = {};

        const notify = (stepId, detail) => {
            steps.push({ id: stepId, detail });
            if (onStep) onStep(stepId, detail);
        };

        const snapshot = (stepId, rows, headers) => {
            snapshots[stepId] = { rows: rows, headers: headers, totalRows: rows.length };
        };

        // 원본 컬럼 헤더 (2D 배열용)
        const rawHeaders = ['col0(과목)', 'col1(학년)', 'col2(학기)', 'col3(번호)', 'col4(성명)', 'col5(내용)', 'col6', 'col7', 'col8', 'col9', 'col10'];

        // 1. 파일 파싱
        const workbook = XLSX.read(fileBuffer, { type: 'array' });
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];

        // 2. 시트를 2D 배열로 변환 (헤더 없이)
        const rawData = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: null });
        notify('parse', `${rawData.length}행 읽음`);
        snapshot('parse', rawData, rawHeaders);

        // 3. 파일 유형 감지 및 분기
        const fileType = this.detectFileType(rawData);
        if (fileType === 'type2') {
            return this.preprocessType2(rawData, filename);
        }

        // Type1 (과목별) 처리
        const stats = {
            originalRows: rawData.length,
            removedRows: 0,
            finalRows: 0,
            subjects: new Set(),
            students: new Set()
        };

        // 3. 파일명에서 학년/반 정보 추출
        const classInfo = this.extractClassInfo(filename);
        notify('extract', classInfo.grade ? `${classInfo.grade}학년 ${classInfo.class}반` : '정보 없음 (파일명 패턴 불일치)');

        // 4. 불필요한 행 제거
        const filteredData = [];
        for (const row of rawData) {
            if (!this.shouldRemoveRow(row)) {
                filteredData.push(row);
            } else {
                stats.removedRows++;
            }
        }
        notify('filter', `${stats.removedRows}행 제거 → ${filteredData.length}행 남음`);
        snapshot('filter', filteredData.map(r => [...r]), rawHeaders);

        // 4-1. 잘린 과목명 병합
        // 과목명(col0)이 한 글자인 행은 줄 넘김으로 잘린 조각이므로
        // 윗 행의 과목명에 이어붙이고, 내용(col5)도 합친 뒤 해당 행을 제거
        let fixedCount = 0;
        for (let i = filteredData.length - 1; i >= 1; i--) {
            const col0 = String(filteredData[i][0] || '').trim();
            if (col0.length === 1) {
                // 윗 행 과목명에 이어붙이기
                const prevSubject = String(filteredData[i - 1][0] || '').trim();
                filteredData[i - 1][0] = prevSubject + col0;

                // 내용(col5)이 있으면 윗 행에 합치기
                const curContent = String(filteredData[i][5] || '').trim();
                if (curContent) {
                    const prevContent = String(filteredData[i - 1][5] || '').trim();
                    filteredData[i - 1][5] = prevContent ? prevContent + ' ' + curContent : curContent;
                }

                filteredData.splice(i, 1);
                fixedCount++;
            }
        }
        notify('fixsubject', fixedCount > 0 ? `${fixedCount}행 병합 → ${filteredData.length}행 남음` : '병합 대상 없음');
        snapshot('fixsubject', filteredData.map(r => [...r]), rawHeaders);

        // 5. Forward Fill - 빈 셀을 위의 값으로 채우기
        // 컬럼 0-4 (과목, 학년, 학기, 번호, 성명)
        const fillColumns = [0, 1, 2, 3, 4];
        let filledCount = 0;
        for (let i = 1; i < filteredData.length; i++) {
            for (const colIdx of fillColumns) {
                if (filteredData[i][colIdx] === null ||
                    filteredData[i][colIdx] === undefined ||
                    String(filteredData[i][colIdx]).trim() === '') {
                    filteredData[i][colIdx] = filteredData[i - 1][colIdx];
                    filledCount++;
                }
            }
        }
        notify('fill', `${filledCount}개 빈 셀 채움`);
        snapshot('fill', filteredData.map(r => [...r]), rawHeaders);

        // 6. 내용이 없는 행 제거
        const dataWithContent = filteredData.filter(row => {
            const content = row[5];
            return content !== null && content !== undefined && String(content).trim() !== '';
        });
        const emptyContentRemoved = filteredData.length - dataWithContent.length;
        notify('validate', `${emptyContentRemoved}행 제거 → ${dataWithContent.length}행 남음`);
        snapshot('validate', dataWithContent.map(r => [...r]), rawHeaders);

        // 7. 같은 과목/학기/학생의 내용 합치기
        const groupedMap = new Map();
        let mergedCount = 0;

        for (const row of dataWithContent) {
            const subject = String(row[0] || '').trim();
            const grade = row[1];
            const semester = row[2];
            const number = row[3];
            const name = String(row[4] || '').trim();
            const content = String(row[5] || '').trim();

            const key = `${subject}|${grade}|${semester}|${number}|${name}`;

            if (groupedMap.has(key)) {
                const existing = groupedMap.get(key);
                existing.content += ' ' + content;
                mergedCount++;
            } else {
                groupedMap.set(key, {
                    subject,
                    grade,
                    semester,
                    number,
                    name,
                    content
                });
                stats.subjects.add(subject);
                stats.students.add(name);
            }
        }
        notify('merge', `${mergedCount}개 항목 병합 → ${groupedMap.size}개 고유 항목`);

        const mergedHeaders = ['과목', '학년', '학기', '번호', '성명', '내용'];
        const mergedRows = Array.from(groupedMap.values()).map(v =>
            [v.subject, v.grade, v.semester, v.number, v.name, v.content]
        );
        snapshot('merge', mergedRows, mergedHeaders);

        // 8. 결과 배열 생성
        const result = [];

        for (const [key, value] of groupedMap) {
            const row = {
                반: classInfo.class,
                학년: value.grade,
                학기: value.semester,
                번호: value.number,
                성명: value.name,
                과목: value.subject,
                내용: value.content
            };
            result.push(row);
        }

        // 9. 정렬: 번호 → 과목 → 학기
        result.sort((a, b) => {
            if (a.번호 !== b.번호) return (a.번호 || 0) - (b.번호 || 0);
            if (a.과목 !== b.과목) return (a.과목 || '').localeCompare(b.과목 || '');
            return (a.학기 || 0) - (b.학기 || 0);
        });

        stats.finalRows = result.length;
        stats.subjects = Array.from(stats.subjects);
        stats.students = Array.from(stats.students);
        notify('sort', `최종 ${result.length}행 (학생 ${stats.students.length}명, 과목 ${stats.subjects.length}개)`);

        const finalHeaders = ['반', '학년', '학기', '번호', '성명', '과목', '내용'];
        const finalRows = result.map(r =>
            [r.반, r.학년, r.학기, r.번호, r.성명, r.과목, r.내용]
        );
        snapshot('sort', finalRows, finalHeaders);

        return { data: result, stats, steps, snapshots };
    },

    /**
     * 전처리 결과를 Excel 파일로 변환
     * @param {Array} data - 전처리된 데이터 배열
     * @param {string} originalFilename - 원본 파일명
     * @returns {Blob} - Excel 파일 Blob
     */
    toExcel(data, originalFilename) {
        // 헤더
        const headers = ['반', '학년', '학기', '번호', '성명', '과목', '내용'];

        // 데이터를 2D 배열로 변환
        const rows = [headers];
        for (const item of data) {
            rows.push([
                item.반,
                item.학년,
                item.학기,
                item.번호,
                item.성명,
                item.과목,
                item.내용
            ]);
        }

        // 워크북 생성
        const ws = XLSX.utils.aoa_to_sheet(rows);

        // 열 너비 설정
        ws['!cols'] = [
            { wch: 5 },   // 반
            { wch: 5 },   // 학년
            { wch: 5 },   // 학기
            { wch: 5 },   // 번호
            { wch: 10 },  // 성명
            { wch: 15 },  // 과목
            { wch: 100 }  // 내용
        ];

        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');

        // Blob으로 변환
        const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        return new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    },

    /**
     * 여러 파일의 전처리 결과를 하나로 합치기
     * @param {Array} processedDataArray - 각 파일의 전처리 결과 배열
     * @returns {Array} - 합쳐진 데이터 배열
     */
    mergeResults(processedDataArray) {
        const merged = [];
        for (const { data } of processedDataArray) {
            merged.push(...data);
        }

        // 정렬: 반 → 번호 → 과목 → 학기
        merged.sort((a, b) => {
            if (a.반 !== b.반) return (a.반 || 0) - (b.반 || 0);
            if (a.번호 !== b.번호) return (a.번호 || 0) - (b.번호 || 0);
            if (a.과목 !== b.과목) return (a.과목 || '').localeCompare(b.과목 || '');
            return (a.학기 || 0) - (b.학기 || 0);
        });

        return merged;
    },

    /**
     * 통계 요약 생성
     */
    generateSummary(stats) {
        return `원본: ${stats.originalRows}행 → 최종: ${stats.finalRows}행 (${stats.removedRows}행 제거)\n` +
               `학생: ${stats.students.length}명\n` +
               `과목: ${stats.subjects.length}개`;
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Preprocessor;
}
