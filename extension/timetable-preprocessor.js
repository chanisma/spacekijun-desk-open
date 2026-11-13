/**
 * 시간표 Excel 파일 전처리 모듈
 * - 학생별 시간표 XLS → DB용 flat CSV 변환
 * - 각 학생 블록: 19행 (날짜, 제목, 학생정보, 헤더, 7교시×2행, 페이지마커)
 * - 출력 컬럼: 학년, 반, 번호, 성명, 요일, 교시, 과목, 교사, 교실
 */

const TimetablePreprocessor = {
    DAYS: ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'],
    ROWS_PER_STUDENT: 19,

    /**
     * 파일명에서 학년/반 추출
     */
    extractClassInfo(filename) {
        const match = filename.match(/Grade(\d+)_Class(\d+)/i);
        if (match) return { grade: parseInt(match[1]), classNum: parseInt(match[2]) };
        return { grade: null, classNum: null };
    },

    /**
     * 학생 정보 행 파싱
     * "2026학년도 1학기 1학년 1반  1번 박하준" → { grade, classNum, number, name }
     */
    parseStudentInfo(row) {
        const text = String(row[0] || '').trim();
        const match = text.match(/(\d+)학년\s*(\d+)반\s+(\d+)번\s+(.+)/);
        if (!match) return null;
        return {
            grade: parseInt(match[1]),
            classNum: parseInt(match[2]),
            number: parseInt(match[3]),
            name: match[4].trim()
        };
    },

    /**
     * 과목(교사) 문자열 파싱
     * "공통수학1(윤하준)" → { subject: "공통수학1", teacher: "윤하준" }
     */
    parseSubjectTeacher(cell) {
        const text = String(cell || '').trim();
        if (!text) return { subject: '', teacher: '' };
        const match = text.match(/^(.+?)\(([^)]+)\)$/);
        if (match) return { subject: match[1].trim(), teacher: match[2].trim() };
        return { subject: text, teacher: '' };
    },

    /**
     * 학생 블록이 시작되는 행인지 확인
     */
    isStudentInfoRow(row) {
        if (!row || row.length === 0) return false;
        const text = String(row[0] || '').trim();
        return /\d+학년\s*\d+반\s+\d+번\s+/.test(text);
    },

    /**
     * 학생 블록 경계 찾기 (학생정보 행 인덱스 목록)
     */
    findStudentBlocks(rawData) {
        const blocks = [];
        for (let i = 0; i < rawData.length; i++) {
            if (this.isStudentInfoRow(rawData[i])) {
                blocks.push(i);
            }
        }
        return blocks;
    },

    /**
     * 한 학생 블록에서 시간표 레코드 추출
     * @param {Array} rawData - 전체 2D 배열
     * @param {number} infoRowIdx - 학생정보 행 인덱스
     * @returns {Array} - flat 레코드 배열
     */
    extractStudentTimetable(rawData, infoRowIdx) {
        const info = this.parseStudentInfo(rawData[infoRowIdx]);
        if (!info) return [];

        const records = [];
        const headerRowIdx = infoRowIdx + 1; // "교  시" 헤더 행

        // 7교시 × 2행 (교실행 + 과목행)
        for (let period = 1; period <= 7; period++) {
            const classroomRowIdx = headerRowIdx + 1 + (period - 1) * 2;
            const subjectRowIdx = classroomRowIdx + 1;

            if (classroomRowIdx >= rawData.length || subjectRowIdx >= rawData.length) break;

            const classroomRow = rawData[classroomRowIdx] || [];
            const subjectRow = rawData[subjectRowIdx] || [];

            // 요일별 (col 1~7: 월~일)
            for (let dayIdx = 0; dayIdx < this.DAYS.length; dayIdx++) {
                const colIdx = dayIdx + 1;
                const classroom = String(classroomRow[colIdx] || '').trim();
                const subjectCell = String(subjectRow[colIdx] || '').trim();

                if (!subjectCell && !classroom) continue;

                const { subject, teacher } = this.parseSubjectTeacher(subjectCell);
                if (!subject) continue;

                records.push({
                    학년: info.grade,
                    반: info.classNum,
                    번호: info.number,
                    성명: info.name,
                    요일: this.DAYS[dayIdx],
                    교시: period,
                    과목: subject,
                    교사: teacher,
                    교실: classroom
                });
            }
        }

        return records;
    },

    /**
     * Excel 파일 전처리 (메인)
     * @param {ArrayBuffer} fileBuffer - 파일 데이터
     * @param {string} filename - 파일명
     * @returns {Object} - { data, stats }
     */
    preprocess(fileBuffer, filename) {
        const workbook = XLSX.read(fileBuffer, { type: 'array' });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rawData = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: null });

        const classInfo = this.extractClassInfo(filename);
        const blocks = this.findStudentBlocks(rawData);

        const allRecords = [];
        for (const blockIdx of blocks) {
            const records = this.extractStudentTimetable(rawData, blockIdx);
            allRecords.push(...records);
        }

        const students = new Set(allRecords.map(r => `${r.번호}_${r.성명}`));
        const subjects = new Set(allRecords.map(r => r.과목));

        return {
            data: allRecords,
            stats: {
                originalRows: rawData.length,
                studentCount: blocks.length,
                recordCount: allRecords.length,
                students: Array.from(students),
                subjects: Array.from(subjects),
                grade: classInfo.grade,
                classNum: classInfo.classNum
            }
        };
    },

    /**
     * 여러 파일 결과 합치기
     */
    mergeResults(processedArray) {
        const merged = [];
        for (const { data } of processedArray) {
            merged.push(...data);
        }
        merged.sort((a, b) => {
            if (a.학년 !== b.학년) return a.학년 - b.학년;
            if (a.반 !== b.반) return a.반 - b.반;
            if (a.번호 !== b.번호) return a.번호 - b.번호;
            const dayOrder = (d) => this.DAYS.indexOf(d);
            if (a.요일 !== b.요일) return dayOrder(a.요일) - dayOrder(b.요일);
            return a.교시 - b.교시;
        });
        return merged;
    },

    /**
     * 데이터를 CSV 문자열로 변환
     */
    toCSV(data) {
        const headers = ['학년', '반', '번호', '성명', '요일', '교시', '과목', '교사', '교실'];
        const escapeCSV = (val) => {
            const str = String(val ?? '');
            if (str.includes(',') || str.includes('"') || str.includes('\n')) {
                return '"' + str.replace(/"/g, '""') + '"';
            }
            return str;
        };
        const lines = [headers.join(',')];
        for (const row of data) {
            lines.push(headers.map(h => escapeCSV(row[h])).join(','));
        }
        return '\ufeff' + lines.join('\n'); // BOM for Excel UTF-8
    },

    /**
     * 데이터를 Excel 파일로 변환
     */
    toExcel(data) {
        const headers = ['학년', '반', '번호', '성명', '요일', '교시', '과목', '교사', '교실'];
        const rows = [headers];
        for (const item of data) {
            rows.push(headers.map(h => item[h]));
        }
        const ws = XLSX.utils.aoa_to_sheet(rows);
        ws['!cols'] = [
            { wch: 5 }, { wch: 5 }, { wch: 5 }, { wch: 10 },
            { wch: 8 }, { wch: 5 }, { wch: 20 }, { wch: 10 }, { wch: 15 }
        ];
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Timetable');
        const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        return new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    }
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = TimetablePreprocessor;
}
