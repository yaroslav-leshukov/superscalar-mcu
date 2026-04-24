import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, DefaultDict
from collections import defaultdict, Counter
from pathlib import Path

@dataclass
class Instruction:
    time_end: int          
    time_exec: str         
    R: str                 
    E: str                 
    CIPC: str              
    INSTR: str             
    FU_REQ: str          
    TAG: int            
    PTR: str             
    CNT: str             
    NIPC: str           
    Reg: str           
    original_line: str     
    line_number: int      

@dataclass
class Packet:
    instructions: List[Instruction]
    start_line: int
    end_line: int
    has_unit_3_or_8: bool
    last_unit_3_or_8_idx: int = -1
    fu_req_counts: Dict[str, int] = field(default_factory=dict)
    unit_sequence_stats: Dict[str, List[int]] = field(default_factory=dict)
    
    def __post_init__(self):
        fu_req_list = [instr.FU_REQ for instr in self.instructions]
        self.fu_req_counts = Counter(fu_req_list)
        
        self.unit_sequence_stats = self._analyze_unit_sequence()
    
    def _analyze_unit_sequence(self) -> Dict[str, List[int]]:
        """
        Анализирует порядковые номера одинаковых юнитов внутри пачки.
        Возвращает словарь: {fu_req: [порядковый_номер_1, порядковый_номер_2, ...]}
        """
        sequence_stats = {}
        unit_counters = defaultdict(int)
        
        for instr in self.instructions:
            fu_req = instr.FU_REQ
            unit_counters[fu_req] += 1  # Увеличиваем счетчик для данного типа юнита
            order_number = unit_counters[fu_req]  # Порядковый номер этого юнита в пачке
            
            if fu_req not in sequence_stats:
                sequence_stats[fu_req] = []
            sequence_stats[fu_req].append(order_number)
        
        return sequence_stats
    
    def get_time_adjustments(self) -> Tuple[int, int, int, int]:
        """
        Вычисляет все корректировки времени для пачки.
        Возвращает: (вычитаемое_время_пакета, вычитаемое_время_инструкций, 
                    прибавляемое_время_юнита_3, общая_корректировка)
        """
        if not self.instructions:
            return 0, 0, 0, 0
        
        n = len(self.instructions)
        
        instructions_subtract = (n - 1) * 10 if n > 1 else 0
        
        packet_subtract = 0
        if self.has_unit_3_or_8 and self.last_unit_3_or_8_idx >= 0:
            last_unit_3_or_8 = self.instructions[self.last_unit_3_or_8_idx]
            last_instr = self.instructions[-1]
            packet_subtract = abs(last_instr.time_end - last_unit_3_or_8.time_end)
        else:
            first_instr = self.instructions[0]
            last_instr = self.instructions[-1]
            packet_subtract = abs(last_instr.time_end - first_instr.time_end)
        
        unit_3_add = self.fu_req_counts.get('3', 0) * 10
        
        total_adjustment = unit_3_add - (packet_subtract + instructions_subtract)
        
        return packet_subtract, instructions_subtract, unit_3_add, total_adjustment
    
    def get_tags(self) -> List[int]:
        """Возвращает список TAG всех инструкций в пачке."""
        return [instr.TAG for instr in self.instructions]
    
    def get_fu_reqs(self) -> List[str]:
        """Возвращает список FU_REQ всех инструкций в пачке."""
        return [instr.FU_REQ for instr in self.instructions]
    
    def get_time_range(self) -> Tuple[int, int]:
        """Возвращает время начала и конца пачки."""
        first_time = self.instructions[0].time_end if self.instructions else 0
        last_time = self.instructions[-1].time_end if self.instructions else 0
        return (first_time, last_time)
    
    def get_unit_sequence_data(self) -> Dict[str, List[Tuple[Instruction, int]]]:
        """
        Возвращает данные о порядке юнитов в пачке.
        {fu_req: [(инструкция, порядковый_номер), ...]}
        """
        result = defaultdict(list)
        unit_counters = defaultdict(int)
        
        for instr in self.instructions:
            fu_req = instr.FU_REQ
            unit_counters[fu_req] += 1
            order_number = unit_counters[fu_req]
            result[fu_req].append((instr, order_number))
        
        return dict(result)

def analyze_unit_order_distribution(packets: List[Packet]) -> Dict[str, Dict[int, Dict[str, float]]]:
    """
    Анализирует распределение инструкций по порядковым номерам юнитов внутри пачек.
    """
    order_stats = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'percentage': 0.0}))
    total_instructions_by_unit = Counter()
    
    for packet in packets:
        for fu_req, order_numbers in packet.unit_sequence_stats.items():
            for order_number in order_numbers:
                order_stats[fu_req][order_number]['count'] += 1
                total_instructions_by_unit[fu_req] += 1
    
    for fu_req in order_stats:
        total_for_unit = total_instructions_by_unit.get(fu_req, 0)
        if total_for_unit > 0:
            for order_number in order_stats[fu_req]:
                order_stats[fu_req][order_number]['percentage'] = (
                    order_stats[fu_req][order_number]['count'] / total_for_unit * 100
                )
    
    return dict(order_stats)

def analyze_concurrent_units(packets: List[Packet]) -> Dict[str, Dict[int, Dict[str, float]]]:
    """
    Анализирует одновременное использование одинаковых функциональных юнитов.
    """
    concurrent_stats = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'percentage': 0.0, 'packets': 0}))
    total_instructions_by_unit = Counter()
    packets_with_concurrency = defaultdict(lambda: defaultdict(set))
    
    for packet_idx, packet in enumerate(packets):
        for fu_req, count in packet.fu_req_counts.items():
            total_instructions_by_unit[fu_req] += count
        
        for fu_req, count in packet.fu_req_counts.items():
            if count > 1:
                concurrent_stats[fu_req][count]['count'] += count
                concurrent_stats[fu_req][count]['packets'] += 1
                packets_with_concurrency[fu_req][count].add(packet_idx)
    
    for fu_req in concurrent_stats:
        total_for_unit = total_instructions_by_unit.get(fu_req, 0)
        if total_for_unit > 0:
            for concurrent_count in concurrent_stats[fu_req]:
                concurrent_stats[fu_req][concurrent_count]['percentage'] = (
                    concurrent_stats[fu_req][concurrent_count]['count'] / total_for_unit * 100
                )
    
    return dict(concurrent_stats)

def analyze_unit_3_usage(packets: List[Packet]) -> Dict[str, any]:
    """
    Анализирует использование юнита 3.
    """
    total_unit_3_count = 0
    packets_with_unit_3 = 0
    
    for packet in packets:
        unit_3_count = packet.fu_req_counts.get('3', 0)
        if unit_3_count > 0:
            total_unit_3_count += unit_3_count
            packets_with_unit_3 += 1
            unit_3_distribution[unit_3_count] += 1
    
    return {
        'total_count': total_unit_3_count,
        'packets_with_unit_3': packets_with_unit_3,
        'total_time_added': total_unit_3_count * 10,
        'distribution': dict(unit_3_distribution)
    }

def parse_file(file_path: str) -> Tuple[List[Instruction], List[str], int]:
    """Парсит файл с трассировкой, возвращает инструкции, заголовки и общее время."""
    instructions = []
    headers = []
    total_time = 0
    line_num = 0
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            
        for line in lines:
            line_num += 1
            line = line.rstrip('\n')
            
            if line.startswith('#') or 'Time Time_Exec' in line:
                headers.append(line)
                continue
            
            if not line.strip():
                headers.append(line)
                continue
            
            parts = line.split()
            
            if len(parts) < 11:
                print(f"Ошибка в строке {line_num}: недостаточно полей")
                continue
            
            try:
                instr = Instruction(
                    time_end=int(parts[0]),
                    time_exec=parts[1],
                    R=parts[2],
                    E=parts[3],
                    CIPC=parts[4],
                    INSTR=parts[5],
                    FU_REQ=parts[6],
                    TAG=int(parts[7]),
                    PTR=parts[8],
                    CNT=parts[9],
                    NIPC=parts[10],
                    Reg=' '.join(parts[11:]) if len(parts) > 11 else '',
                    original_line=line,
                    line_number=line_num
                )
                instructions.append(instr)
                total_time = max(total_time, instr.time_end)
                
            except (ValueError, IndexError) as e:
                print(f"Ошибка парсинга строки {line_num}: {e}")
                continue
                
    except Exception as e:
        print(f"Ошибка чтения файла: {e}")
        sys.exit(1)
    
    return instructions, headers, total_time

def find_packets(instructions: List[Instruction]) -> List[Packet]:
    """Находит все пачки в инструкциях."""
    packets = []
    current_packet = []
    in_packet = False
    start_line = 0
    
    for i, instr in enumerate(instructions):
        if instr.TAG == 0:
            if in_packet and current_packet:
                has_unit_3_or_8 = False
                last_unit_3_or_8_idx = -1
                
                for idx, p_instr in enumerate(current_packet):
                    if p_instr.FU_REQ in ['3', '8']:
                        has_unit_3_or_8 = True
                        last_unit_3_or_8_idx = idx
                
                packet = Packet(
                    instructions=current_packet.copy(),
                    start_line=start_line,
                    end_line=instructions[i-1].line_number,
                    has_unit_3_or_8=has_unit_3_or_8,
                    last_unit_3_or_8_idx=last_unit_3_or_8_idx
                )
                packets.append(packet)
                current_packet = []
                in_packet = False
            
            current_packet = [instr]
            start_line = instr.line_number
            in_packet = True
        elif in_packet:
            current_packet.append(instr)
    
    if in_packet and current_packet:
        has_unit_3_or_8 = False
        last_unit_3_or_8_idx = -1
        
        for idx, p_instr in enumerate(current_packet):
            if p_instr.FU_REQ in ['3', '8']:
                has_unit_3_or_8 = True
                last_unit_3_or_8_idx = idx
        
        packet = Packet(
            instructions=current_packet.copy(),
            start_line=start_line,
            end_line=instructions[-1].line_number,
            has_unit_3_or_8=has_unit_3_or_8,
            last_unit_3_or_8_idx=last_unit_3_or_8_idx
        )
        packets.append(packet)
    
    return packets

def format_instruction(instr: Instruction, offset: int = 0) -> str:
    """Форматирует инструкцию для вывода с возможным смещением."""
    indent = ' ' * offset
    
    parts = [
        f"{instr.time_end: >6}",
        f"{instr.time_exec: >7}",
        f"{instr.R: >1}",
        f"{instr.E: >1}",
        f"{instr.CIPC: >16}",
        f"{instr.INSTR: >8}",
        f"{instr.FU_REQ: >3}",
        f"{instr.TAG: >10}",
        f"{instr.PTR: >6}",
        f"{instr.CNT: >6}",
        f"{instr.NIPC: >16}",
    ]
    
    if instr.Reg:
        parts.append(instr.Reg)
    
    return indent + ' '.join(parts)

def write_packets_info(packets: List[Packet], output_file: str, total_time: int,
                      concurrent_stats: Dict[str, Dict[int, Dict[str, float]]],
                      order_stats: Dict[str, Dict[int, Dict[str, float]]],
                      unit_3_stats: Dict[str, any]):
    """Записывает информацию о пачках в файл."""
    with open(output_file, 'w') as f:
        f.write("Информация о пачках инструкций\n")
        f.write("=" * 80 + "\n\n")
        
        total_packet_subtract = 0
        total_instructions_subtract = 0
        total_unit_3_add = 0
        total_adjustment = 0
        
        for i, packet in enumerate(packets, 1):
            packet_subtract, instructions_subtract, unit_3_add, packet_adjustment = packet.get_time_adjustments()
            total_packet_subtract += packet_subtract
            total_instructions_subtract += instructions_subtract
            total_unit_3_add += unit_3_add
            total_adjustment += packet_adjustment
            
            f.write(f"Пачка #{i} (строки {packet.start_line}-{packet.end_line}):\n")
            f.write(f"  Количество инструкций: {len(packet.instructions)}\n")
            f.write(f"  Теги: {packet.get_tags()}\n")
            f.write(f"  FU_REQ: {packet.get_fu_reqs()}\n")
            f.write(f"  Распределение юнитов: {dict(packet.fu_req_counts)}\n")
            
            f.write(f"  Порядковые номера юнитов:\n")
            unit_sequence_data = packet.get_unit_sequence_data()
            for fu_req in sorted(unit_sequence_data.keys()):
                instructions_info = []
                for instr, order_num in unit_sequence_data[fu_req]:
                    instructions_info.append(f"{order_num}-й {fu_req}")
                f.write(f"    Юнит {fu_req}: {', '.join(instructions_info)}\n")
            
            f.write(f"  Время пачки: {packet.get_time_range()[0]} -> {packet.get_time_range()[1]}\n")
            f.write(f"  Содержит юниты 3/8: {'Да' if packet.has_unit_3_or_8 else 'Нет'}\n")
            f.write(f"  Вычитаемое время параллельности: {packet_subtract}\n")
            f.write(f"  Вычитаемое время инструкций ((N-1)*10): {instructions_subtract}\n")
            f.write(f"  Прибавляемое время за юнит 3 (кол-во*10): {unit_3_add}\n")
            f.write(f"  Общая корректировка времени: {packet_adjustment}\n")
            f.write(f"  Инструкции:\n")
            
            for instr in packet.instructions:
                f.write(f"    {instr.original_line}\n")
            
            f.write("\n")
        
        f.write("=" * 80 + "\n")
        f.write(f"ОБЩАЯ СТАТИСТИКА КОРРЕКТИРОВКИ ВРЕМЕНИ:\n")
        f.write(f"  Общее время выполнения: {total_time}\n")
        f.write(f"  Суммарное вычитаемое время параллельности: {total_packet_subtract}\n")
        f.write(f"  Суммарное вычитаемое время инструкций: {total_instructions_subtract}\n")
        f.write(f"  Суммарное прибавляемое время за юниты 3: {total_unit_3_add}\n")
        f.write(f"  Итоговая корректировка времени: {total_adjustment}\n")
        f.write(f"  Новое общее время: {total_time + total_adjustment}\n")
        
        if total_time > 0:
            packet_percent = (total_packet_subtract / total_time) * 100
            instr_percent = (total_instructions_subtract / total_time) * 100
            unit_3_percent = (total_unit_3_add / total_time) * 100
            adjustment_percent = (abs(total_adjustment) / total_time) * 100
            
            f.write(f"  Процент вычитаемого времени параллельности: {packet_percent:.2f}%\n")
            f.write(f"  Процент вычитаемого времени инструкций: {instr_percent:.2f}%\n")
            f.write(f"  Процент прибавляемого времени за юниты 3: {unit_3_percent:.2f}%\n")
            f.write(f"  Процент итоговой корректировки: {adjustment_percent:.2f}%\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ ЮНИТА 3:\n")
        f.write("-" * 80 + "\n")
        f.write(f"  Всего инструкций с юнитом 3: {unit_3_stats['total_count']}\n")
        f.write(f"  Пачек, содержащих юнит 3: {unit_3_stats['packets_with_unit_3']}\n")
        f.write(f"  Всего прибавляемого времени: {unit_3_stats['total_time_added']}\n")
        f.write(f"  Распределение по пачкам:\n")
        
        for count, packet_count in sorted(unit_3_stats['distribution'].items()):
            f.write(f"    {count} юнит(ов) 3 в пачке: {packet_count} пачек\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("Статистика одновременного использования функциональных юнитов:\n")
        f.write("-" * 80 + "\n")
        
        for fu_req in sorted(concurrent_stats.keys()):
            f.write(f"\nФункциональный юнит {fu_req}:\n")
            for count in sorted(concurrent_stats[fu_req].keys()):
                stats = concurrent_stats[fu_req][count]
                f.write(f"  Одновременно {count} юнитов: {stats['count']} инструкций ")
                f.write(f"({stats['percentage']:.1f}%), ")
                f.write(f"в {stats['packets']} пачках\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("РАСПРЕДЕЛЕНИЕ ИНСТРУКЦИЙ ПО ПОРЯДКОВЫМ НОМЕРАМ ЮНИТОВ:\n")
        f.write("-" * 80 + "\n")
        
        for fu_req in sorted(order_stats.keys()):
            f.write(f"\nФункциональный юнит {fu_req}:\n")
            
            max_order = max(order_stats[fu_req].keys())
            total_for_unit = sum(order_stats[fu_req][o]['count'] for o in order_stats[fu_req])
            
            f.write(f"  Всего инструкций с юнитом {fu_req}: {total_for_unit}\n")
            
            for order_num in range(1, max_order + 1):
                if order_num in order_stats[fu_req]:
                    stats = order_stats[fu_req][order_num]
                    f.write(f"  {order_num}-й юнит {fu_req}: {stats['count']} инструкций ")
                    f.write(f"({stats['percentage']:.1f}%)\n")
                else:
                    f.write(f"  {order_num}-й юнит {fu_req}: 0 инструкций (0.0%)\n")

def main():
    input_file = "/home/physdesign/RVC_perf_impact/sc_riscv/tracelogs_RVB/rv64/hiperf/1_fu/dhrystone_5k_iters_rv64_hiperf_1_fu_4_way.txt"
    output_file = "trace_processed.txt"
    packets_info_file = "packets_info.txt"
    rearrange_instructions = False
    
    print("Парсинг файла...")
    instructions, headers, total_time = parse_file(input_file)
    
    print(f"Найдено инструкций: {len(instructions)}")
    print(f"Общее время выполнения: {total_time}")
    
    packets = find_packets(instructions)
    print(f"Найдено пачек: {len(packets)}")
    
    
    print("\nАнализ статистики использования юнитов...")
    concurrent_stats = analyze_concurrent_units(packets)
    order_stats = analyze_unit_order_distribution(packets)
    unit_3_stats = analyze_unit_3_usage(packets)
    
    
    total_packet_subtract = 0
    total_instructions_subtract = 0
    total_unit_3_add = 0
    total_adjustment = 0
    
    for packet in packets:
        packet_subtract, instructions_subtract, unit_3_add, packet_adjustment = packet.get_time_adjustments()
        total_packet_subtract += packet_subtract
        total_instructions_subtract += instructions_subtract
        total_unit_3_add += unit_3_add
        total_adjustment += packet_adjustment
    
    new_total_time = total_time + total_adjustment
    
    print(f"\nИТОГОВАЯ КОРРЕКТИРОВКА ВРЕМЕНИ:")
    print(f"Общее время выполнения: {total_time}")
    print(f"Вычитаемое время параллельности (пакеты): {total_packet_subtract}")
    print(f"Вычитаемое время инструкций ((N-1)*10): {total_instructions_subtract}")
    print(f"Прибавляемое время за юниты 3 (кол-во*10): {total_unit_3_add}")
    print(f"Суммарная корректировка: {total_adjustment}")
    print(f"Новое общее время: {new_total_time}")
    
    if total_time > 0:
        packet_percent = (total_packet_subtract / total_time) * 100
        instr_percent = (total_instructions_subtract / total_time) * 100
        unit_3_percent = (total_unit_3_add / total_time) * 100
        adjustment_percent = (abs(total_adjustment) / total_time) * 100
        
        print(f"\nВ процентном соотношении:")
        print(f"  Вычитание параллельности: {packet_percent:.2f}%")
        print(f"  Вычитание инструкций: {instr_percent:.2f}%")
        print(f"  Прибавление за юниты 3: {unit_3_percent:.2f}%")
        print(f"  Итоговая корректировка: {adjustment_percent:.2f}%")
    
    
    print("\n" + "=" * 60)
    print("СТАТИСТИКА ЮНИТА 3:")
    print("=" * 60)
    print(f"Всего инструкций с юнитом 3: {unit_3_stats['total_count']}")
    print(f"Пачек, содержащих юнит 3: {unit_3_stats['packets_with_unit_3']}")
    print(f"Всего прибавляемое время: {unit_3_stats['total_time_added']}")
    print(f"Распределение по пачкам:")
    
    for count, packet_count in sorted(unit_3_stats['distribution'].items()):
        print(f"  • {count} юнит(ов) 3 в пачке: {packet_count} пачек")
    
    
    print("\n" + "=" * 60)
    print("РАСПРЕДЕЛЕНИЕ ПО ПОРЯДКОВЫМ НОМЕРАМ ЮНИТОВ")
    print("=" * 60)
    
    for fu_req in sorted(order_stats.keys()):
        print(f"\nФункциональный юнит {fu_req}:")
        
        total_for_unit = sum(order_stats[fu_req][o]['count'] for o in order_stats[fu_req])
        print(f"  Всего инструкций: {total_for_unit}")
        
        max_order = max(order_stats[fu_req].keys())
        for order_num in range(1, max_order + 1):
            if order_num in order_stats[fu_req]:
                stats = order_stats[fu_req][order_num]
                print(f"  • {order_num}-й юнит {fu_req}: {stats['count']} инструкций "
                      f"({stats['percentage']:.1f}%)")
                      
if __name__ == "__main__":
    main()
