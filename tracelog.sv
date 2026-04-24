module tracelog;
typedef logic       [31:0]                              type_fu_req_v;
typedef logic       [31:0]                              type_cipc_v;
typedef type_cipc_v [REST_ISSUE_WIDTH-1:0]             type_cipc_ss_v;
typedef logic       [IDU_HAZARD_CNT_WIDTH-1:0]         type_no_haz_cntr_ss_v;


type_id_req_s                                               fu_req;
logic           [ID_HAZARD_CNT_WIDTH-1:0]                   ss_no_hazards_way_cnt;
type_id_queue_s [REST_ISSUE_WIDTH-1:0]                     instr_curr_ss_rest;
logic                            [31:0]                     func_unit_req;
type_fu_req_v                    [0:7]                      fu_req_queue;
type_fu_req_v                    [0:7]                      fu_req_queue_new;
type_fu_req_v                    [0:1]                      fu_req_queue_new2;
logic                            [31:0]                     rf_fu_req_log0;
logic                            [31:0]                     rf_fu_req_log1;
type_cipc_ss_v                   [0:7]                      ss_next_cipc_queue_new;
type_cipc_ss_v                   [0:1]                      ss_next_cipc_queue_new2;
type_cipc_ss_v                   [0:7]                      ss_next_cipc_queue;
type_no_haz_cntr_ss_v            [0:7]                      ss_no_haz_cntr_queue_new;
type_no_haz_cntr_ss_v            [0:1]                      ss_no_haz_cntr_queue_new2;
type_no_haz_cntr_ss_v            [0:7]                      ss_no_haz_cntr_queue;
type_no_haz_cntr_ss_v                                       rf_nhaz_cntr_log0;
type_no_haz_cntr_ss_v                                       rf_nhaz_cntr_log1;
logic                            [31:0]                     rf_ss_cipc_log;
logic                            [31:0]                     tag_ff;
logic                            [31:0]                     tag0;
logic                            [31:0]                     tag1;
logic                                                       new_commit_of_instr;
logic                                                       curr_element_last_in_slot;
logic                                                       next_element_last_in_slot;
logic                                                       slot_ss_update;
logic                                                       curr_slot_cnt_empty;
logic                                                       next_slot_cnt_empty;
logic                                                       skip_slot;
logic                                                       slot_reset;
type_cipc_ss_v                                              slot_cipc_ss_next;
type_cipc_ss_v                                              slot_cipc_ss;
type_no_haz_cntr_ss_v                                       slot_no_haz_cntr_ss_next;
type_no_haz_cntr_ss_v                                       slot_no_haz_cntr_ss;
logic                                                       not_match_cipc;
logic                                                       not_match_cipc0_x;
logic                                                       not_match_cipc1_x;
logic                                                       not_match_cipc0;
logic                                                       not_match_cipc1;
logic                                                       zero_instr_ss;
logic                                                       zero_instr_ss_ff;
logic                                                       ss_cipc_rd_ptr_update;
logic                                                       ss_cipc_rd_ptr_clr;
logic                                                       retire_last_element_in_slot;
type_no_haz_cntr_ss_v                                       ss_cipc_rd_ptr;
type_no_haz_cntr_ss_v                                       ss_cipc_rd_ptr_next;
logic                                                       ss_cipc_rd_ptr_en;
logic                                                       tag_update;
logic                                                       next_slot_cnt_1;
logic                            [31:0]                     rf_tag_log0;
logic                            [31:0]                     rf_tag_log1;
type_no_haz_cntr_ss_v                                       rf_rd_ptr_log0;
type_no_haz_cntr_ss_v                                       rf_rd_ptr_log0_next;
type_no_haz_cntr_ss_v                                       rf_rd_ptr_log1;
type_no_haz_cntr_ss_v                                       rf_rd_ptr_log1_next;
logic                                                       display_tag0;
logic                                                       display_tag1;

always_comb begin
    case (1'b1)
        fu_req.cfu_req : begin
            func_unit_req = 'd1;
        end
        fu_req.alu_req : begin
            func_unit_req = 'd2;
        end
        fu_req.lsu_req : begin
            func_unit_req = 'd3;
        end
        fu_req.bmu_req : begin
            func_unit_req = 'd4;
        end
        fu_req.fpu_req : begin
            func_unit_req = 'd5;
        end
        fu_req.dsp_req : begin
            func_unit_req = 'd6;
        end
        fu_req.crypto_req : begin
            func_unit_req = 'd7;
        end
        fu_req.mdu_req : begin
            func_unit_req = 'd8;
        end
        default: begin
            func_unit_req = 'd0;
        end
    endcase
end
//-------------------------------------------------------------------------------
// Logic for SUPERSCALAR processing
//-------------------------------------------------------------------------------
`ifdef _SUPERSCALAR
assign new_commit_of_instr          = (|csr_instret_en) | (~csr_irq_req & (csr_exc_req | csr_eret_req));
assign curr_element_last_in_slot    = ((ss_cipc_rd_ptr + 1'b1) == slot_no_haz_cntr_ss);
assign next_element_last_in_slot    = ((ss_cipc_rd_ptr + 2'd2) == slot_no_haz_cntr_ss);
assign retire_last_element_in_slot  = (zero_instr_ss) ? ((ss_cipc_rd_ptr + 1'b1) == ss_no_haz_cntr_queue_new2[0])
                                                      : ((csr_instret_en[1] & next_element_last_in_slot) | curr_element_last_in_slot);
assign skip_slot                    = (csr_instret_en[1] & (not_match_cipc1 | (curr_element_last_in_slot & ~not_match_cipc0))) 
                                      | (zero_instr_ss & next_slot_cnt_empty);
assign slot_reset                   = (retire_last_element_in_slot & ~(not_match_cipc | (csr_instret_en[1] & curr_element_last_in_slot)));

always_comb begin
   if (slot_reset) begin
        slot_cipc_ss_next        = '0;
        slot_no_haz_cntr_ss_next = '0;
    end else if (skip_slot) begin
        for (int i = 0; i < _REST_ISSUE_WIDTH; i++) begin 
            slot_cipc_ss_next[i] = $isunknown(ss_next_cipc_queue_new2[1][i]) ? '0 : ss_next_cipc_queue_new2[1][i];
        end
        slot_no_haz_cntr_ss_next = $isunknown(ss_no_haz_cntr_queue_new2[1])  ? '0 : ss_no_haz_cntr_queue_new2[1];
    end else begin
        for (int i = 0; i < _REST_ISSUE_WIDTH; i++) begin 
            slot_cipc_ss_next[i] = $isunknown(ss_next_cipc_queue_new2[0][i]) ? '0 : ss_next_cipc_queue_new2[0][i];
        end
        slot_no_haz_cntr_ss_next = $isunknown(ss_no_haz_cntr_queue_new2[0])  ? '0 : ss_no_haz_cntr_queue_new2[0];
    end
end

assign curr_slot_cnt_empty          = ~|slot_no_haz_cntr_ss;
assign next_slot_cnt_empty          = $isunknown(ss_no_haz_cntr_queue_new2[0]) ? '1 : ~|ss_no_haz_cntr_queue_new2[0];
assign slot_ss_update               = (new_commit_of_instr & (curr_slot_cnt_empty | not_match_cipc | retire_last_element_in_slot));
assign zero_instr_ss                =  new_commit_of_instr &  curr_slot_cnt_empty & csr_instret_en[1];

always_ff @(negedge rst_n, posedge clk) begin
    if (~rst_n) begin
        slot_cipc_ss        <= 'x;
        slot_no_haz_cntr_ss <= '0;
    end else begin
        if (slot_ss_update) begin
            slot_cipc_ss        <= slot_cipc_ss_next;
            slot_no_haz_cntr_ss <= slot_no_haz_cntr_ss_next;
        end
    end
end

assign ss_cipc_rd_ptr_update = new_commit_of_instr & (~curr_slot_cnt_empty | zero_instr_ss) & ~(zero_instr_ss & retire_last_element_in_slot);
assign ss_cipc_rd_ptr_clr    = wb_wb2epu_clr | (zero_instr_ss ? (not_match_cipc1 | next_slot_cnt_empty) : slot_ss_update);
assign not_match_cipc        = (zero_instr_ss) ? not_match_cipc1 
                                               : ((not_match_cipc0) | (csr_instret_en[1] & not_match_cipc1));

assign not_match_cipc0   = $isunknown(not_match_cipc0_x) ? '1 : not_match_cipc0_x;
assign not_match_cipc1   = $isunknown(not_match_cipc1_x) ? '1 : not_match_cipc1_x;                                         
assign not_match_cipc0_x = (slot_cipc_ss[ss_cipc_rd_ptr] != cipc_queue_new2[0]);
assign not_match_cipc1_x = (zero_instr_ss) ? (ss_next_cipc_queue_new2[0][ss_cipc_rd_ptr] != cipc_queue_new2[1]) 
                                           : (slot_cipc_ss[ss_cipc_rd_ptr + 1'b1] != cipc_queue_new2[1]);

always_comb begin
    ss_cipc_rd_ptr_next   = ss_cipc_rd_ptr;
    if (ss_cipc_rd_ptr_clr) begin
        ss_cipc_rd_ptr_next = '0;
    end else if (zero_instr_ss) begin
        ss_cipc_rd_ptr_next = ss_cipc_rd_ptr + 1'd1;
    end else if (ss_cipc_rd_ptr_update) begin
        ss_cipc_rd_ptr_next = (csr_instret_en[1]) ? (ss_cipc_rd_ptr + 2'd2) 
                                                  : (ss_cipc_rd_ptr + 1'd1);
    end
end

assign ss_cipc_rd_ptr_en = ss_cipc_rd_ptr_update | ss_cipc_rd_ptr_clr;

always_ff @(negedge rst_n, posedge clk) begin
    if (~rst_n) begin
        ss_cipc_rd_ptr <= '0;
    end else begin
        if (ss_cipc_rd_ptr_en)  begin
            ss_cipc_rd_ptr <= ss_cipc_rd_ptr_next;
        end
    end
end

assign display_tag0 = (zero_instr_ss) ? '0 
                                      : (ss_cipc_rd_ptr_update & ~not_match_cipc0);
assign display_tag1 = (zero_instr_ss) ?  (~not_match_cipc1 & ~next_slot_cnt_empty) 
                                      : (ss_cipc_rd_ptr_update & ~(not_match_cipc | curr_element_last_in_slot));

always_comb begin
    tag0 = '0;
    tag1 = '0;
    if (display_tag0) begin
        tag0 = tag_ff;
    end
    if (display_tag1) begin
        tag1 = tag_ff;
    end
end

assign next_slot_cnt_1 = $isunknown(ss_no_haz_cntr_queue_new2[0]) ? '0 : (ss_no_haz_cntr_queue_new2[0] == 1'b1);
assign tag_update      = (display_tag0 & slot_ss_update) | (zero_instr_ss & next_slot_cnt_1 & display_tag1);

always_ff @(negedge rst_n, posedge clk) begin
    if (~rst_n)  begin
        tag_ff <= '0;
    end else begin
        if (tag_update) begin
            tag_ff <= tag_ff + 1'b1;
        end
    end
end

always_ff @(negedge rst_n, posedge clk) begin
    if (~rst_n)  begin
        zero_instr_ss_ff <= '0;
    end else begin
        if (zero_instr_ss_ff & ~zero_instr_ss) begin
            zero_instr_ss_ff <= 1'b0;
        end else begin
            zero_instr_ss_ff <= zero_instr_ss;
        end
    end
end

assign rf_rd_ptr_log0_next = (zero_instr_ss_ff) ? '0 : ss_cipc_rd_ptr;
assign rf_rd_ptr_log1_next = (zero_instr_ss & (~not_match_cipc1 & ~next_slot_cnt_empty)) ? 1'b1 
                                                        : ((ss_cipc_rd_ptr_update & ~(not_match_cipc | curr_element_last_in_slot)) ? (ss_cipc_rd_ptr + 1'b1) 
                                                                                                                                   : '0);

always_ff @(posedge clk) begin
    if (~rst_n) begin
        rf_tag_log0    <= 'x;
        rf_tag_log1    <= 'x;
        rf_rd_ptr_log0 <= 'x;
        rf_rd_ptr_log1 <= 'x;
    end else begin
        rf_tag_log0    <= tag0;
        rf_tag_log1    <= tag1;
        rf_rd_ptr_log0 <= rf_rd_ptr_log0_next;
        rf_rd_ptr_log1 <= rf_rd_ptr_log1_next;
    end
end
endmodule